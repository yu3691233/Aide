"""
task_monitor.py
统一单线程任务监控：Git commit 轮询 + worktree 变化检测 + IDE 进程监控
零侵入：不修改项目任何文件，不使用 git hook
"""
import os
import sys
import time
import threading
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
from paths import PROJECT_ROOT


def _get_task_runtime():
    from task_runtime import TaskRuntime
    return TaskRuntime(str(BASE_DIR))


class TaskMonitor:
    """统一单线程任务监控，无活跃任务时几乎零开销"""

    def __init__(self, check_interval=60, worktree_timeout_min=10):
        self.check_interval = check_interval
        self.worktree_timeout_min = worktree_timeout_min
        self._running = False
        self._thread = None
        self._last_commit_hash = None
        self._last_worktree_mtime = {}  # ide -> mtime
        self._known_ide_pids = {}  # ide -> set of pids

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"TaskMonitor started (interval={self.check_interval}s)")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                if self._has_active_tasks():
                    self._check_git()
                    self._check_worktree()
                    self._check_processes()
            except Exception as e:
                logger.error(f"TaskMonitor error: {e}")
            time.sleep(self.check_interval)

    def _has_active_tasks(self):
        try:
            runtime = _get_task_runtime()
            ide_status = runtime.read_ide_status()
            return any(s.get("status") == "busy" for s in ide_status.values())
        except Exception:
            return False

    def _check_git(self):
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%H"],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                cwd=str(PROJECT_ROOT), timeout=3, creationflags=flags
            )
            if result.returncode != 0:
                return
            current_hash = result.stdout.strip()
            if not current_hash:
                return
            if self._last_commit_hash is None:
                self._last_commit_hash = current_hash
                return
            if current_hash == self._last_commit_hash:
                return
            self._last_commit_hash = current_hash
            self._on_new_commit(current_hash)
        except Exception as e:
            logger.error(f"Git check error: {e}")

    def _on_new_commit(self, commit_hash):
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%s", commit_hash],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                cwd=str(PROJECT_ROOT), timeout=3, creationflags=flags
            )
            commit_msg = result.stdout.strip() if result.returncode == 0 else ""

            result2 = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                cwd=str(PROJECT_ROOT), timeout=3, creationflags=flags
            )
            changed_files = [
                f.strip() for f in result2.stdout.strip().splitlines() if f.strip()
            ] if result2.returncode == 0 else []

            runtime = _get_task_runtime()
            ide_status = runtime.read_ide_status()

            for ide, status in ide_status.items():
                if status.get("status") != "busy":
                    continue
                task_id = status.get("current_task_id")
                if not task_id:
                    continue
                task = runtime.get_task(task_id)
                if not task or task.get("status") not in ("running", "dispatched"):
                    continue

                owned = task.get("owned_paths", [])
                if owned and changed_files:
                    matched = any(
                        any(f.startswith(op.rstrip("/")) or op.rstrip("/").startswith(f) for op in owned)
                        for f in changed_files
                    )
                    if not matched:
                        continue

                short_hash = commit_hash[:8]
                runtime.mark_task_done(task_id, summary=f"Git commit: {short_hash} - {commit_msg}")
                logger.info(f"[TaskMonitor] Task {task_id} ({ide}) done (commit {short_hash})")

                from event_bus import bus
                bus.publish("task.done", {
                    "task_id": task_id,
                    "target_ide": ide,
                    "reason": "git_commit",
                    "commit": short_hash,
                    "message": commit_msg,
                })
        except Exception as e:
            logger.error(f"Commit match error: {e}")

    def _check_worktree(self):
        try:
            runtime = _get_task_runtime()
            ide_status = runtime.read_ide_status()
            now = time.time()

            for ide, status in ide_status.items():
                if status.get("status") != "busy":
                    self._last_worktree_mtime.pop(ide, None)
                    continue
                task_id = status.get("current_task_id")
                if not task_id:
                    continue
                task = runtime.get_task(task_id)
                if not task or task.get("status") != "running":
                    continue

                worktree = task.get("worktree_path")
                if not worktree or not os.path.isdir(worktree):
                    continue

                latest_mtime = self._dir_latest_mtime(worktree)
                if latest_mtime == 0:
                    continue

                prev = self._last_worktree_mtime.get(ide)
                if prev is None:
                    self._last_worktree_mtime[ide] = latest_mtime
                    continue

                if latest_mtime > prev:
                    self._last_worktree_mtime[ide] = latest_mtime
                else:
                    elapsed_min = (now - latest_mtime) / 60
                    if elapsed_min >= self.worktree_timeout_min:
                        logger.info(f"[TaskMonitor] Task {task_id} ({ide}) worktree idle {elapsed_min:.0f}min")
                        from event_bus import bus
                        bus.publish("task.possibly_done", {
                            "task_id": task_id,
                            "target_ide": ide,
                            "idle_minutes": round(elapsed_min, 1),
                            "reason": "worktree_no_changes",
                        })
                        del self._last_worktree_mtime[ide]
        except Exception as e:
            logger.error(f"Worktree check error: {e}")

    def _dir_latest_mtime(self, path):
        latest = 0
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        mt = os.path.getmtime(fp)
                        if mt > latest:
                            latest = mt
                    except Exception:
                        pass
        except Exception:
            pass
        return latest

    def _check_processes(self):
        try:
            import psutil
        except ImportError:
            return

        try:
            runtime = _get_task_runtime()
            ide_status = runtime.read_ide_status()

            for ide, status in ide_status.items():
                if status.get("status") != "busy":
                    self._known_ide_pids.pop(ide, None)
                    continue

                task_id = status.get("current_task_id")
                if not task_id:
                    continue

                current_pids = self._get_ide_pids(ide)
                prev_pids = self._known_ide_pids.get(ide, set())

                if prev_pids and not current_pids:
                    task = runtime.get_task(task_id)
                    if task and task.get("status") == "running":
                        runtime.mark_task_done(task_id, summary=f"IDE {ide} 进程退出，自动标记完成")
                        logger.info(f"[TaskMonitor] Task {task_id} ({ide}) done (process exit)")
                        from event_bus import bus
                        bus.publish("task.done", {
                            "task_id": task_id,
                            "target_ide": ide,
                            "reason": "ide_process_exit",
                        })

                self._known_ide_pids[ide] = current_pids
        except Exception as e:
            logger.error(f"Process check error: {e}")

    def _get_ide_pids(self, ide_name):
        pids = set()
        try:
            import psutil
            for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                    if ide_name.lower() in name or ide_name.lower() in cmdline:
                        pids.add(proc.info["pid"])
                except Exception:
                    pass
        except Exception:
            pass
        return pids


_monitor = TaskMonitor()


def start_all_monitors():
    _monitor.start()
