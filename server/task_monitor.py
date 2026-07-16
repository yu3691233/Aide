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

    # 委派任务类型集合：result_ref_required=true 时这些类型不得被 git commit 自动推进。
    # 目的：防止 read_only/research/test/summary 或 owned_paths=[] 的委派任务被
    # 主 IDE 在任务开始前留下的旧提交抢先推进 pending_test，造成 result_ref=null 死锁。
    # 仅作用于 metadata.result_ref_required=true 的委派任务；普通任务保持既有自动完成语义。
    _NO_AUTO_COMPLETE_TYPES = {"read_only", "research", "test", "summary"}

    @staticmethod
    def _skip_auto_complete(task):
        """是否跳过 git commit 自动完成（仅保护 result_ref_required=true 的委派任务）。

        - 非 result_ref_required 的普通任务：一律不跳过，保持既有自动完成语义；
        - result_ref_required=true 且 read_only/research/test/summary：无文件归属证据，跳过；
        - result_ref_required=true 且 owned_paths=[]：无文件匹配证据，跳过；
        - result_ref_required=true 且 code+owned_paths 非空：允许自动完成，
          调用方写入 commit:<hash> result_ref 以满足 verify 闭环。
        """
        metadata = task.get("metadata") or {}
        if not metadata.get("result_ref_required"):
            # 普通任务（包括 research/test/summary 或 owned_paths=[]）保持原自动完成行为。
            return False
        task_type = str(metadata.get("task_type") or "").lower()
        if task_type in TaskMonitor._NO_AUTO_COMPLETE_TYPES:
            return True
        if not task.get("owned_paths"):
            return True
        return False

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

                # 只读/测试/总结/无 owned_paths 委派任务不得仅凭 git commit 自动推进；
                # 旧提交（含任务开始前主 IDE 的提交）会落入此分支被跳过，等待 worker 显式回传。
                if self._skip_auto_complete(task):
                    logger.info(
                        f"[TaskMonitor] Skip auto-complete for task {task_id} ({ide}): "
                        f"no file ownership evidence, awaiting worker report"
                    )
                    continue

                owned = task.get("owned_paths", [])
                # 有 owned_paths 的代码任务：保持既有文件匹配语义。
                if owned and changed_files:
                    matched = any(
                        any(f.startswith(op.rstrip("/")) or op.rstrip("/").startswith(f) for op in owned)
                        for f in changed_files
                    )
                    if not matched:
                        continue

                # 委派任务（result_ref_required）必须带可验证的 result_ref 才能进入 pending_test，
                # 否则 verify 闭环拒绝（mcp_server.handle_verify_delegated_task L379-380）形成死锁。
                # 非 result_ref_required 的旧 code 任务保持原行为（result_ref=None）。
                metadata = task.get("metadata") or {}
                result_ref = (
                    f"commit:{commit_hash}"
                    if metadata.get("result_ref_required") else None
                )
                short_hash = commit_hash[:8]
                runtime.mark_task_done(
                    task_id,
                    summary=f"Git commit: {short_hash} - {commit_msg}",
                    result_ref=result_ref,
                )
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
                        # result_ref_required 委派任务进程退出可能是崩溃而非显式完成：
                        # mark_task_done 不带 result_ref 会进入 pending_test 死锁
                        # （verify 闭环 mcp_server.handle_verify_delegated_task L379-380 拒绝）。
                        # 改为 mark_task_failed 让主 IDE 决定重派或读取已有证据，
                        # worker 仍可通过 fail_delegated_aidelink_task 补传 result_ref。
                        metadata = task.get("metadata") or {}
                        if metadata.get("result_ref_required"):
                            runtime.mark_task_failed(
                                task_id,
                                error=f"IDE {ide} 进程退出（result_ref_required 任务不得自动完成，等待 worker 显式回传）",
                            )
                            logger.info(
                                f"[TaskMonitor] Task {task_id} ({ide}) failed (process exit, result_ref_required)"
                            )
                            from event_bus import bus
                            bus.publish("task.failed", {
                                "task_id": task_id,
                                "target_ide": ide,
                                "reason": "ide_process_exit_result_ref_required",
                            })
                        else:
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
