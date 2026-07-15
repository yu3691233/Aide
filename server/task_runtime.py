import difflib
import hashlib
import json
import os
import shutil
import threading
import time
from datetime import datetime, timedelta

from event_bus import bus
from json_utils import safe_read_json, safe_write_json
from paths import PROJECT_ROOT


def _load_supported_ides():
    """从 ide_registry.json 和 manual_ides.json 动态加载支持的 IDE 列表。

    manual_ides.json 保存用户手动添加的 IDE（如 WorkBuddy），必须合并进来，
    否则 App 端发送消息时会被 SUPPORTED_IDES 检查拒绝，消息无法写入剪切板。
    inject_to_ide.py 的 else 分支已支持自定义 IDE 注入（通过窗口绑定）。
    """
    keys = set()
    try:
        from ide_scanner import load_registry
        registry = load_registry()
        keys.update(registry.keys())
    except Exception:
        pass
    try:
        from paths import MANUAL_IDES_FILE
        manual_list = safe_read_json(MANUAL_IDES_FILE, default=[])
        for item in manual_list:
            k = item.get("key")
            if k:
                keys.add(k)
    except Exception:
        pass
    if not keys:
        return ("trae", "trae_cn", "antigravity_ide", "oc", "mimo")
    return tuple(keys)


class _SupportedIdeKeys:
    def _keys(self):
        return _load_supported_ides()

    def __contains__(self, item):
        return item in self._keys()

    def __iter__(self):
        return iter(self._keys())

    def __len__(self):
        return len(self._keys())

    def __repr__(self):
        return repr(self._keys())


def get_supported_ides():
    """获取支持的 IDE 列表（动态）"""
    return _load_supported_ides()


# 兼容旧代码：SUPPORTED_IDES 作为属性访问
SUPPORTED_IDES = _SupportedIdeKeys()


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _detect_git_version():
    """从 git 检测当前代码版本（tag 或 commit hash）"""
    try:
        import subprocess
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        # 优先用最近的 tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=PROJECT_ROOT, timeout=3, creationflags=flags
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # 无 tag 则用 commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=PROJECT_ROOT, timeout=3, creationflags=flags
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _detect_app_version():
    from version_utils import detect_app_version
    return detect_app_version()


def _future_iso(minutes=30):
    return (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class TaskRuntime:
    # TaskRuntime is intentionally lightweight and is created by several route
    # handlers.  The timeout scanner, however, must be process-wide: starting a
    # daemon thread from every instance causes the thread count (and eventually
    # memory usage) to grow for the lifetime of the bridge process.
    _timeout_scanner_lock = threading.Lock()
    _timeout_scanner_threads = {}
    _state_lock_registry_lock = threading.Lock()
    _state_locks = {}

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.state_dir = os.path.join(base_dir, "state")
        self.queues_dir = os.path.join(base_dir, "queues")
        self.results_dir = os.path.join(base_dir, "results")
        self.worktrees_dir = os.path.join(base_dir, "worktrees")
        self.ide_status_file = os.path.join(self.state_dir, "ide_status.json")
        self.leases_file = os.path.join(self.state_dir, "leases.json")
        # 同一桥接目录的运行时实例共享可重入锁，避免不同请求实例的
        # 读改写操作互相覆盖。
        self._lock = self._get_state_lock(base_dir)
        self.ensure_storage()
        # 迁移旧版 task_context.json 到统一状态机
        self.migrate_from_task_context()
        self._ensure_timeout_scanner()

    @classmethod
    def _get_state_lock(cls, base_dir):
        key = os.path.normcase(os.path.abspath(base_dir))
        with cls._state_lock_registry_lock:
            lock = cls._state_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._state_locks[key] = lock
            return lock

    def _ensure_timeout_scanner(self):
        """Ensure one timeout scanner exists for this bridge data directory.

        Routes may construct ``TaskRuntime`` for each request, so the scanner
        cannot be owned by an individual instance.  Keep the registry keyed by
        the normalized base directory to preserve support for isolated test or
        embedded runtimes while preventing duplicate scanners in production.
        """
        key = os.path.normcase(os.path.abspath(self.base_dir))
        with self._timeout_scanner_lock:
            scanner = self._timeout_scanner_threads.get(key)
            if scanner is not None and scanner.is_alive():
                return
            scanner = threading.Thread(
                target=self._timeout_scanner_loop,
                daemon=True,
                name=f"TaskRuntimeTimeoutScanner:{os.path.basename(key) or key}",
            )
            self._timeout_scanner_threads[key] = scanner
            scanner.start()

    @property
    def tasks_file(self):
        from config import load_settings
        settings = load_settings()
        project_dir = settings.get("project_dir", "")
        if project_dir and os.path.isdir(project_dir):
            import hashlib
            h = hashlib.md5(os.path.normpath(project_dir).lower().encode('utf-8')).hexdigest()[:8]
            folder_name = "".join(c for c in os.path.basename(project_dir) if c.isalnum()) or "proj"
            f = os.path.join(self.state_dir, f"tasks_{folder_name}_{h}.json")
            global_tasks_file = os.path.join(self.state_dir, "tasks.json")
            if not os.path.exists(f) or os.path.getsize(f) <= 4:
                if os.path.exists(global_tasks_file) and os.path.getsize(global_tasks_file) > 4:
                    try:
                        import shutil
                        shutil.copyfile(global_tasks_file, f)
                        print(f"[TaskRuntime] Migrated global tasks.json to {f}", flush=True)
                    except Exception as e:
                        print(f"[TaskRuntime] Failed to migrate global tasks: {e}", flush=True)
                        self._ensure_json_file(f, [])
                else:
                    self._ensure_json_file(f, [])
            return f
        f = os.path.join(self.state_dir, "tasks.json")
        self._ensure_json_file(f, [])
        return f

    def ensure_storage(self):
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.queues_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        self._ensure_json_file(self.tasks_file, [])
        self._ensure_json_file(self.ide_status_file, self._default_ide_status())
        self._ensure_json_file(self.leases_file, {})
        for ide in SUPPORTED_IDES:
            queue_path = self._queue_path(ide)
            if not os.path.exists(queue_path):
                with open(queue_path, "w", encoding="utf-8") as f:
                    f.write("")

    def _ensure_json_file(self, path, default_value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            return
        safe_write_json(path, default_value)

    def _default_ide_status(self):
        now = _now_iso()
        return {
            ide: {
                "ide": ide,
                "status": "idle",
                "current_task_id": None,
                "lease_expires_at": None,
                "last_heartbeat_at": now,
                "error": None,
            }
            for ide in SUPPORTED_IDES
        }

    def _queue_path(self, ide):
        return os.path.join(self.queues_dir, f"{ide}.jsonl")

    def read_tasks(self):
        with self._lock:
            return safe_read_json(self.tasks_file, [])

    def write_tasks(self, tasks):
        with self._lock:
            safe_write_json(self.tasks_file, tasks)
            self.sync_current_task_md(tasks)

    def sync_current_task_md(self, tasks):
        try:
            from paths import get_project_root
            proj_root = get_project_root()
            if not proj_root or not os.path.isdir(proj_root):
                return

            md_path = os.path.join(proj_root, "CURRENT_TASK.md")

            if not tasks:
                if os.path.exists(md_path):
                    try:
                        os.remove(md_path)
                    except Exception:
                        pass
                return

            lines = [
                "# 📋 AideLink 当前项目开发任务",
                "",
                "本文件由 AideLink 自动生成与同步。当您（Agent）在本工作区开发时，应当主动阅读此文件以了解任务状态和开发要求。",
                "",
                "## 活跃任务 (待办 / 进行中)"
            ]

            active_count = 0
            completed_count = 0

            for t in tasks:
                status = t.get("status", "pending")
                if status in ("pending", "running"):
                    status_symbol = "⏳ 待办" if status == "pending" else "🏃 进行中"
                    title = t.get("title") or "无标题"
                    lines.append(f"- [{status_symbol}] **ID**: `{t.get('task_id')}` | **{title}**")
                    if t.get("description"):
                        lines.append(f"  * 描述: {t.get('description')}")
                    active_count += 1

            if active_count == 0:
                lines.append("- (暂无活跃任务)")

            lines.append("")
            lines.append("## 历史任务 (已完成 / 失败)")
            for t in tasks:
                status = t.get("status", "pending")
                if status in ("completed", "failed"):
                    status_symbol = "✅ 已完成" if status == "completed" else "❌ 失败"
                    title = t.get("title") or "无标题"
                    lines.append(f"- [{status_symbol}] **ID**: `{t.get('task_id')}` | **{title}**")
                    completed_count += 1

            if completed_count == 0:
                lines.append("- (暂无历史任务)")

            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("### 💡 Agent 任务流操作指南：")
            lines.append("当您认领或完成任务时，请通过 HTTP 调用本地 AideLink 接口进行同步：")
            lines.append("1. **认领并开始开发**:")
            lines.append("   `curl -X POST http://127.0.0.1:5000/api/tasks/<task_id>/assign`")
            lines.append("2. **开发完成标记**:")
            lines.append("   `curl -X POST http://127.0.0.1:5000/api/tasks/<task_id>/complete`")
            lines.append("3. **标记开发失败**:")
            lines.append("   `curl -X POST http://127.0.0.1:5000/api/tasks/<task_id>/fail`")

            # 写入文件
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            print(f"[TaskRuntime] Failed to sync CURRENT_TASK.md: {e}", flush=True)

    def read_ide_status(self):
        with self._lock:
            status = safe_read_json(self.ide_status_file, self._default_ide_status())
            changed = False
            for ide, default in self._default_ide_status().items():
                if ide not in status:
                    status[ide] = default
                    changed = True
            if changed:
                self.write_ide_status(status)
            return status

    def write_ide_status(self, status):
        with self._lock:
            safe_write_json(self.ide_status_file, status)

    def read_leases(self):
        with self._lock:
            return safe_read_json(self.leases_file, {})

    def write_leases(self, leases):
        with self._lock:
            safe_write_json(self.leases_file, leases)

    def new_task_id(self):
        return f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"

    def _get_current_project(self):
        try:
            from config import load_settings
            s = load_settings()
            return s.get("current_project", "") or s.get("project_dir", "") or ""
        except Exception:
            return ""

    def create_task(
        self,
        text,
        title=None,
        source="phone",
        target_ide=None,
        image=None,
        owned_paths=None,
        parent_task_id=None,
        priority="medium",
        metadata=None,
        app_version=None,
    ):
        with self._lock:
            task_id = self.new_task_id()
            normalized_target = target_ide if target_ide in SUPPORTED_IDES else None
            status = "queued" if normalized_target else "draft"
            git_version = _detect_git_version()
            task = {
                "task_id": task_id,
                "parent_task_id": parent_task_id,
                "title": title or (text[:60] if text else task_id),
                "text": text,
                "source": source,
                "target_ide": normalized_target,
                "project": self._get_current_project(),
                "status": status,
                "priority": priority,
                "image": image,
                "owned_paths": owned_paths or [],
                "worktree_path": None,
                "result_ref": None,
                "summary": None,
                "error": None,
                "metadata": metadata or {},
                "app_version": app_version or _detect_app_version() or "",
                "git_version": git_version or "",
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "queued_at": _now_iso() if normalized_target else None,
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
            }
            tasks = self.read_tasks()
            tasks.append(task)
            self.write_tasks(tasks)
            if normalized_target:
                self.append_queue_event(normalized_target, "queued", {"task_id": task_id})
            bus.publish("task.created", {
                "task_id": task_id,
                "target_ide": normalized_target,
                "owned_paths": task["owned_paths"],
                "title": task["title"],
                "source": source,
                "priority": priority,
            })
            if normalized_target:
                bus.publish("task.queued", {
                    "task_id": task_id,
                    "target_ide": normalized_target,
                })
            return task

    def list_tasks(self, target_ide=None, status=None, limit=None):
        with self._lock:
            tasks = self.read_tasks()
            if target_ide:
                tasks = [task for task in tasks if task.get("target_ide") == target_ide]
            if status:
                tasks = [task for task in tasks if task.get("status") == status]
            tasks = sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True)
            if limit:
                tasks = tasks[:limit]
            return tasks

    def get_task(self, task_id):
        with self._lock:
            for task in self.read_tasks():
                if task.get("task_id") == task_id:
                    return task
            return None

    def update_task(self, task_id, **fields):
        with self._lock:
            tasks = self.read_tasks()
            updated = None
            old_status = None
            is_manual = fields.pop("_is_manual", False)
            for task in tasks:
                if task.get("task_id") == task_id:
                    old_status = task.get("status")
                    task.update(fields)
                    task["updated_at"] = _now_iso()
                    updated = task
                    break
            if updated is not None:
                self.write_tasks(tasks)
                new_status = updated.get("status")
                if new_status != old_status:
                    event_data = {
                        "task_id": task_id,
                        "target_ide": updated.get("target_ide"),
                        "title": updated.get("title", ""),
                        "status": new_status,
                        "error": updated.get("error"),
                        "summary": updated.get("summary"),
                        "is_manual": is_manual,
                    }
                    if new_status == "done":
                        bus.publish("task.done", event_data)
                    elif new_status in ("failed", "test_failed", "merge_conflict"):
                        bus.publish("task.failed", event_data)
                    elif new_status == "pending_test":
                        bus.publish("task.pending_test", event_data)
                    elif new_status == "running":
                        bus.publish("task.running", event_data)
            return updated

    def assign_task(self, task_id, ide):
        if ide not in SUPPORTED_IDES:
            return None
        with self._lock:
            task = self.update_task(
                task_id,
                target_ide=ide,
                status="queued",
                queued_at=_now_iso(),
                worktree_path=None,
            )
            if task:
                self.append_queue_event(ide, "queued", {"task_id": task_id})
                bus.publish("task.assigned", {
                    "task_id": task_id,
                    "target_ide": ide,
                })
                bus.publish("task.queued", {
                    "task_id": task_id,
                    "target_ide": ide,
                })
            return task

    def mark_task_running(self, task_id, ide):
        with self._lock:
            task = self.get_task(task_id)
            dispatched_at = task.get("dispatched_at") if task else None
            return self.update_task(
                task_id,
                target_ide=ide,
                status="running",
                dispatched_at=dispatched_at or _now_iso(),
                started_at=_now_iso(),
            )

    def mark_task_done(self, task_id, summary=None, result_ref=None, is_manual=False):
        """IDE 报告完成 → 状态变为 pending_test（等待用户验证）"""
        with self._lock:
            task = self.get_task(task_id)
            if not task:
                return None
            self.release_leases(task_id)
            released_ide = None
            if task.get("target_ide") in SUPPORTED_IDES:
                current = self.get_ide_status(task.get("target_ide"))
                if current.get("current_task_id") == task_id:
                    self.release_ide(task.get("target_ide"))
                    released_ide = task.get("target_ide")
            updated = self.update_task(
                task_id,
                status="pending_test",
                summary=summary,
                result_ref=result_ref,
                error=None,
                _is_manual=is_manual,
            )
        # 锁外推进队列：IDE 释放后自动派发下一个 queued 任务
        if released_ide:
            threading.Thread(
                target=self._try_dispatch_next_queued,
                args=(released_ide,),
                daemon=True,
            ).start()
        return updated

    def confirm_task_done(self, task_id, is_manual=False):
        """用户手动确认通过 → testing/test_failed → done"""
        with self._lock:
            return self.update_task(
                task_id,
                status="done",
                completed_at=_now_iso(),
                _is_manual=is_manual,
            )

    def mark_task_failed(self, task_id, error, is_manual=False):
        with self._lock:
            task = self.get_task(task_id)
            if not task:
                return None
            self.release_leases(task_id)
            released_ide = None
            if task.get("target_ide") in SUPPORTED_IDES:
                current = self.get_ide_status(task.get("target_ide"))
                if current.get("current_task_id") == task_id:
                    self.release_ide(task.get("target_ide"), error=error)
                    released_ide = task.get("target_ide")
            updated = self.update_task(
                task_id,
                status="failed",
                error=error,
                completed_at=_now_iso(),
                _is_manual=is_manual,
            )
        if released_ide:
            threading.Thread(
                target=self._try_dispatch_next_queued,
                args=(released_ide,),
                daemon=True,
            ).start()
        return updated

    def mark_task_timeout(self, task_id):
        """任务超时 → 状态置为 timeout，释放租约和 IDE 占用"""
        with self._lock:
            task = self.get_task(task_id)
            if not task:
                return None
            released = self.release_leases(task_id)
            released_ide = None
            if task.get("target_ide") in SUPPORTED_IDES:
                current = self.get_ide_status(task.get("target_ide"))
                if current.get("current_task_id") == task_id:
                    self.release_ide(task.get("target_ide"), error="任务超时")
                    released_ide = task.get("target_ide")
            updated = self.update_task(
                task_id,
                status="timeout",
                error="任务执行超时（超过 30 分钟）",
                completed_at=_now_iso(),
            )
            bus.publish("task.timeout", {
                "task_id": task_id,
                "target_ide": task.get("target_ide"),
                "error": "任务执行超时",
                "released_leases": released,
            })
        if released_ide:
            threading.Thread(
                target=self._try_dispatch_next_queued,
                args=(released_ide,),
                daemon=True,
            ).start()
        return updated

    def append_queue_event(self, ide, event_type, payload):
        if ide not in SUPPORTED_IDES:
            return
        # append 模式单独加锁，避免与 JSON 写入交叉
        with self._lock:
            entry = {
                "timestamp": _now_iso(),
                "ide": ide,
                "event": event_type,
                "payload": payload,
            }
            os.makedirs(self.queues_dir, exist_ok=True)
            with open(self._queue_path(ide), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def next_task_for_ide(self, ide):
        if ide not in SUPPORTED_IDES:
            return None
        with self._lock:
            queued = [
                task for task in self.read_tasks()
                if task.get("target_ide") == ide and task.get("status") == "queued"
            ]
            queued.sort(key=lambda item: item.get("queued_at") or item.get("created_at") or "")
            return queued[0] if queued else None

    def get_ide_status(self, ide=None):
        with self._lock:
            status = self.read_ide_status()
            if ide:
                return status.get(ide)
            return status

    def set_ide_status(self, ide, status, current_task_id=None, lease_minutes=30, error=None):
        if ide not in SUPPORTED_IDES:
            return None
        with self._lock:
            all_status = self.read_ide_status()
            all_status[ide] = {
                "ide": ide,
                "status": status,
                "current_task_id": current_task_id,
                "lease_expires_at": _future_iso(lease_minutes) if status == "busy" else None,
                "last_heartbeat_at": _now_iso(),
                "error": error,
            }
            self.write_ide_status(all_status)
            bus.publish(f"ide.{status}", {
                "ide": ide,
                "current_task_id": current_task_id,
                "lease_expires_at": all_status[ide]["lease_expires_at"],
                "error": error,
            })
            return all_status[ide]

    def heartbeat_ide(self, ide, status=None, current_task_id=None, error=None):
        if ide not in SUPPORTED_IDES:
            return None
        with self._lock:
            all_status = self.read_ide_status()
            current = all_status.get(ide, self._default_ide_status()[ide])
            previous_status = current.get("status")
            if status:
                current["status"] = status
            if current_task_id is not None:
                current["current_task_id"] = current_task_id
            current["last_heartbeat_at"] = _now_iso()
            if current["status"] == "busy" and not current.get("lease_expires_at"):
                current["lease_expires_at"] = _future_iso(30)
            if error is not None:
                current["error"] = error
            all_status[ide] = current
            self.write_ide_status(all_status)
            bus.publish("ide.heartbeat", {
                "ide": ide,
                "status": current["status"],
                "current_task_id": current.get("current_task_id"),
                "previous_status": previous_status,
            })
            return current

    def release_ide(self, ide, error=None):
        return self.set_ide_status(ide, "idle", current_task_id=None, error=error)

    def _try_dispatch_next_queued(self, ide):
        """IDE 释放后自动派发该 IDE 下最早的 queued 任务（后台线程调用）。

        解决：App 建任务恒传 auto_dispatch=false，任务落 queued 后无人派发；
        任务完成后 IDE 释放却无队列推进，导致新任务一直排队。
        """
        if not ide or ide not in SUPPORTED_IDES:
            return
        try:
            if not self.is_ide_available(ide):
                return
            next_task = self.next_task_for_ide(ide)
            if not next_task:
                return
            # 延迟 import 避免循环依赖
            from dispatch_utils import dispatch_task
            ok, msg = dispatch_task(next_task, self)
            tid = next_task.get("task_id")
            if ok:
                print(f"[Queue] Auto-dispatched queued task {tid} to {ide}", flush=True)
            else:
                print(f"[Queue] Auto-dispatch failed for {tid}: {msg}", flush=True)
        except Exception as e:
            print(f"[Queue] Auto-dispatch error for {ide}: {e}", flush=True)

    def is_ide_available(self, ide):
        current = self.get_ide_status(ide)
        if not current:
            return False
        if current.get("status") != "busy":
            return True
        expires = _parse_iso(current.get("lease_expires_at"))
        return expires is None or expires <= datetime.now()

    def acquire_leases(self, task_id, owner, owned_paths, lease_minutes=30):
        owned_paths = [path for path in (owned_paths or []) if isinstance(path, str) and path.strip()]
        if not owned_paths:
            return True, None
        with self._lock:
            leases = self.read_leases()
            now = datetime.now()
            changed = False
            for path, lease in list(leases.items()):
                expires = _parse_iso(lease.get("expires_at"))
                if expires and expires <= now:
                    leases.pop(path, None)
                    changed = True
            for path in owned_paths:
                existing = leases.get(path)
                if existing and existing.get("task_id") != task_id:
                    bus.publish("lease.conflict", {
                        "task_id": task_id,
                        "owner": owner,
                        "path": path,
                        "existing_task_id": existing.get("task_id"),
                        "existing_owner": existing.get("owner"),
                    })
                    return False, path
            for path in owned_paths:
                leases[path] = {
                    "task_id": task_id,
                    "owner": owner,
                    "expires_at": _future_iso(lease_minutes),
                }
                changed = True
            if changed:
                self.write_leases(leases)
            bus.publish("lease.granted", {
                "task_id": task_id,
                "owner": owner,
                "paths": owned_paths,
                "expires_at": _future_iso(lease_minutes),
            })
            return True, None

    def release_leases(self, task_id):
        with self._lock:
            leases = self.read_leases()
            released_paths = []
            changed = False
            for path, lease in list(leases.items()):
                if lease.get("task_id") == task_id:
                    released_paths.append(path)
                    leases.pop(path, None)
                    changed = True
            if changed:
                self.write_leases(leases)
            if released_paths:
                bus.publish("lease.released", {
                    "task_id": task_id,
                    "paths": released_paths,
                })
            return changed

    def _resolve_project_path(self, rel_path):
        rel_path = (rel_path or "").replace("\\", "/").lstrip("/")
        if not rel_path or rel_path.startswith(".."):
            return None
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel_path))
        if not abs_path.startswith(os.path.normpath(PROJECT_ROOT)):
            return None
        return abs_path

    def _hash_file(self, abs_path):
        try:
            with open(abs_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _read_text(self, abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception:
                return ""
        except FileNotFoundError:
            return ""
        except Exception:
            return ""

    def _ensure_worktree_dir(self, task):
        worktree = task.get("worktree_path")
        if not worktree:
            target_ide = task.get("target_ide")
            if target_ide not in SUPPORTED_IDES:
                return None
            worktree = os.path.join(self.worktrees_dir, f"{task['task_id']}-{target_ide}")
            self.update_task(task["task_id"], worktree_path=worktree)
        os.makedirs(worktree, exist_ok=True)
        original_dir = os.path.join(worktree, "original")
        result_dir = os.path.join(worktree, "result")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)
        return worktree

    def prepare_worktree(self, task_id):
        task = self.get_task(task_id)
        if not task:
            return None, "Task not found"
        worktree = self._ensure_worktree_dir(task)
        if not worktree:
            return None, "Task has no assigned IDE"

        snapshot = []
        original_dir = os.path.join(worktree, "original")
        result_dir = os.path.join(worktree, "result")
        for rel_path in task.get("owned_paths", []):
            abs_path = self._resolve_project_path(rel_path)
            if not abs_path:
                continue
            file_hash = self._hash_file(abs_path)
            content = self._read_text(abs_path)
            target = os.path.join(original_dir, rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
            result_target = os.path.join(result_dir, rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(result_target), exist_ok=True)
            with open(result_target, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
            snapshot.append({
                "rel_path": rel_path,
                "abs_path": abs_path,
                "sha256": file_hash,
                "size": len(content.encode("utf-8", errors="replace")),
            })

        self.update_task(
            task_id,
            worktree_path=worktree,
            worktree_snapshot=snapshot,
            worktree_prepared_at=_now_iso(),
        )
        bus.publish("task.worktree_ready", {
            "task_id": task_id,
            "target_ide": task.get("target_ide"),
            "worktree": worktree,
            "files": [item["rel_path"] for item in snapshot],
        })
        return {"worktree": worktree, "files": snapshot}, None

    def update_worktree_file(self, task_id, rel_path, content):
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
        worktree = task.get("worktree_path")
        if not worktree:
            return False, "Worktree not prepared"
        safe_rel = (rel_path or "").replace("\\", "/").lstrip("/")
        if not safe_rel or safe_rel.startswith(".."):
            return False, "Invalid path"
        target = os.path.join(worktree, "result", safe_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", errors="replace") as f:
            f.write(content)
        bus.publish("task.worktree_file_updated", {
            "task_id": task_id,
            "path": safe_rel,
            "bytes": len(content.encode("utf-8", errors="replace")),
        })
        return True, None

    def collect_patch(self, task_id):
        task = self.get_task(task_id)
        if not task:
            return None, "Task not found"
        worktree = task.get("worktree_path")
        if not worktree:
            return None, "Worktree not prepared"
        original_dir = os.path.join(worktree, "original")
        result_dir = os.path.join(worktree, "result")

        changes = []
        owned_paths = task.get("owned_paths", [])
        if not owned_paths and os.path.exists(result_dir):
            detected_paths = []
            for root, dirs, files in os.walk(result_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, result_dir).replace(os.sep, "/")
                    detected_paths.append(rel_path)
            if detected_paths:
                owned_paths = detected_paths
                task["owned_paths"] = detected_paths
                self.update_task(task_id, owned_paths=detected_paths)

        for rel_path in owned_paths:
            original_path = os.path.join(original_dir, rel_path.replace("/", os.sep))
            result_path = os.path.join(result_dir, rel_path.replace("/", os.sep))
            original_text = self._read_text(original_path)
            result_text = self._read_text(result_path)
            if original_text == result_text:
                continue
            original_lines = original_text.splitlines(keepends=True)
            result_lines = result_text.splitlines(keepends=True)
            diff = "".join(difflib.unified_diff(
                original_lines,
                result_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            ))
            changes.append({
                "rel_path": rel_path,
                "original_sha256": self._hash_file(original_path),
                "result_sha256": self._hash_file(result_path),
                "diff": diff,
            })

        if not changes:
            return {"patch": "", "files": [], "stats": {"changed_files": 0, "additions": 0, "deletions": 0}}, None

        patch_text = "\n".join(item["diff"] for item in changes) + "\n"
        additions = 0
        deletions = 0
        for item in changes:
            for line in item["diff"].split("\n"):
                if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                    continue
                if line.startswith("+"):
                    additions += 1
                elif line.startswith("-"):
                    deletions += 1

        patch_dir = os.path.join(self.results_dir, task_id)
        os.makedirs(patch_dir, exist_ok=True)
        patch_file = os.path.join(patch_dir, "patch.diff")
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(patch_text)

        stats = {"changed_files": len(changes), "additions": additions, "deletions": deletions}
        self.update_task(task_id, patch_file=patch_file, patch_stats=stats, patch_collected_at=_now_iso())
        bus.publish("task.patch_collected", {
            "task_id": task_id,
            "patch_file": patch_file,
            "stats": stats,
            "files": [item["rel_path"] for item in changes],
        })
        return {"patch": patch_text, "files": changes, "stats": stats, "patch_file": patch_file}, None

    def apply_patch(self, task_id, conflicts="abort", force=False):
        if conflicts not in ("abort", "skip", "overwrite"):
            return None, "Invalid conflicts policy"
        task = self.get_task(task_id)
        if not task:
            return None, "Task not found"
        worktree = task.get("worktree_path")
        if not worktree:
            return None, "Worktree not prepared"
        result_dir = os.path.join(worktree, "result")

        applied = []
        skipped = []
        failed = []
        owned_paths = task.get("owned_paths", [])
        if not owned_paths and os.path.exists(result_dir):
            detected_paths = []
            for root, dirs, files in os.walk(result_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, result_dir).replace(os.sep, "/")
                    detected_paths.append(rel_path)
            if detected_paths:
                owned_paths = detected_paths
                task["owned_paths"] = detected_paths
                self.update_task(task_id, owned_paths=detected_paths)

        for rel_path in owned_paths:
            abs_path = self._resolve_project_path(rel_path)
            if not abs_path:
                failed.append({"rel_path": rel_path, "reason": "invalid path"})
                continue
            result_path = os.path.join(result_dir, rel_path.replace("/", os.sep))
            if not os.path.exists(result_path):
                failed.append({"rel_path": rel_path, "reason": "result file missing"})
                continue
            result_hash = self._hash_file(result_path)
            live_hash = self._hash_file(abs_path)
            snapshot_entry = next((s for s in task.get("worktree_snapshot", []) if s.get("rel_path") == rel_path), None)
            base_hash = snapshot_entry.get("sha256") if snapshot_entry else None
            if live_hash != base_hash and conflicts == "abort" and not force:
                failed.append({
                    "rel_path": rel_path,
                    "reason": "live file changed since snapshot",
                    "live_sha256": live_hash,
                    "base_sha256": base_hash,
                })
                continue
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                shutil.copyfile(result_path, abs_path)
                applied.append({"rel_path": rel_path, "sha256": result_hash})
            except Exception as exc:
                failed.append({"rel_path": rel_path, "reason": str(exc)})

        if failed and conflicts == "abort" and not force:
            self.update_task(task_id, merge_status="aborted", merge_attempts=(task.get("merge_attempts", 0) + 1))
            bus.publish("task.merge_aborted", {
                "task_id": task_id,
                "conflicts": conflicts,
                "applied": applied,
                "failed": failed,
            })
            return {"applied": applied, "skipped": skipped, "failed": failed, "aborted": True}, None

        self.update_task(
            task_id,
            merge_status="merged" if not failed else "partial",
            merged_at=_now_iso(),
            merge_attempts=(task.get("merge_attempts", 0) + 1),
        )
        bus.publish("task.merge_merged", {
            "task_id": task_id,
            "conflicts": conflicts,
            "status": "merged" if not failed else "partial",
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
        })
        return {"applied": applied, "skipped": skipped, "failed": failed, "aborted": False}, None

    def drop_worktree(self, task_id):
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
        worktree = task.get("worktree_path")
        removed = bool(worktree and os.path.isdir(worktree))
        if removed:
            shutil.rmtree(worktree, ignore_errors=True)
        self.update_task(task_id, worktree_path=None, worktree_snapshot=[])
        bus.publish("task.worktree_dropped", {
            "task_id": task_id,
            "removed": removed,
        })
        return True, None

    def _timeout_scanner_loop(self):
        """后台守护线程：每 5 分钟扫描一次，将 dispatched/running 超过 30 分钟的任务标记为 timeout"""
        while True:
            try:
                time.sleep(300)
                now = datetime.now()
                with self._lock:
                    tasks = self.read_tasks()
                for task in tasks:
                    status = task.get("status")
                    if status not in ("dispatched", "running"):
                        continue
                    # 优先用 started_at，其次 dispatched_at
                    ref_str = task.get("started_at") or task.get("dispatched_at")
                    if not ref_str:
                        continue
                    ref_dt = _parse_iso(ref_str)
                    if not ref_dt:
                        continue
                    if (now - ref_dt).total_seconds() > 30 * 60:
                        try:
                            self.mark_task_timeout(task.get("task_id"))
                        except Exception:
                            pass
            except Exception:
                # 守护线程不能因异常退出
                time.sleep(60)

    def migrate_from_task_context(self):
        """迁移旧版 task_context.json 到统一状态机 state/tasks.json"""
        legacy_file = os.path.join(self.base_dir, "task_context.json")
        if not os.path.exists(legacy_file):
            return
        try:
            with open(legacy_file, "r", encoding="utf-8", errors="replace") as f:
                legacy_data = json.load(f)
        except Exception:
            return
        if not isinstance(legacy_data, dict):
            return
        contexts = legacy_data.get("contexts")
        if not isinstance(contexts, dict) or not contexts:
            return
        with self._lock:
            tasks = self.read_tasks()
            existing_ids = {t.get("task_id") for t in tasks if isinstance(t, dict)}
            changed = False
            for tid, ctx in contexts.items():
                if not isinstance(ctx, dict):
                    continue
                if tid in existing_ids:
                    continue
                message_text = ctx.get("message", "")
                title = ctx.get("title") or (message_text[:60] if message_text else tid)
                migrated_task = {
                    "task_id": tid,
                    "parent_task_id": None,
                    "title": title,
                    "text": message_text,
                    "source": "migrated",
                    "target_ide": ctx.get("target_ide"),
                    "status": ctx.get("status", "pending"),
                    "priority": "medium",
                    "image": None,
                    "owned_paths": [],
                    "worktree_path": None,
                    "result_ref": None,
                    "summary": ctx.get("response_preview"),
                    "error": ctx.get("error"),
                    "metadata": {"migrated_from": "task_context"},
                    "app_version": ctx.get("version") or "",
                    "git_version": "",
                    "created_at": ctx.get("time") or _now_iso(),
                    "updated_at": ctx.get("updated_at") or _now_iso(),
                    "queued_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                }
                tasks.append(migrated_task)
                changed = True
            if changed:
                self.write_tasks(tasks)
        # 迁移完成后将旧文件重命名为 .bak
        try:
            bak_path = legacy_file + ".bak"
            os.replace(legacy_file, bak_path)
        except Exception:
            pass
