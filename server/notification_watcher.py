"""
Windows Toast 通知监控模块

通过轮询 Windows 通知数据库（wpndatabase.db）捕获桌面 IDE 的任务完成通知。
纯标准库实现，零外部依赖。

原理：
- Windows 把所有 Toast 通知持久化到 SQLite 数据库
- 复制数据库副本（避免 WAL 锁），查询新增通知
- 通过 AUMID 识别来源 IDE，解析 Payload XML 提取任务信息
- 发布事件到 EventBus，供 App 端 SSE 消费
"""

import os
import shutil
import sqlite3
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from json_utils import safe_read_json, safe_write_json
from datetime import datetime, timedelta
from pathlib import Path

# 默认 IDE AUMID 映射表（可通过配置文件覆盖）
# 注意：Trae 有多个系列（Trae Solo CN / Trae Solo / Trae 国际版），必须按系列区分到不同 ide_key，
# 否则用户同时安装并打开多个系列时，派发与通知会串台。
# 派发键应与 manual_ides.json 的 key 一致（如 trae_solo_cn），这样 ide_status[<key>].current_task_id
# 才能和通知落点对上，_auto_update_task_status 才找得到任务。
DEFAULT_AUMID_MAP = {
    # Trae Solo CN（国内版）→ trae_solo_cn，与 manual_ides.json 的 trae_solo_cn 派发键/窗口绑定对齐
    "ByteDance.TraeSoloCN": "trae_solo_cn",
    # Trae Solo（国际版 Solo）→ trae_solo。AUMID 为推测值，待真实样本验证。
    "ByteDance.TraeSolo": "trae_solo",
    # Trae 国际版 → trae（若用户装了国际版，派发键用 trae）
    "ByteDance.Trae": "trae",
    "Cursor": "cursor",
    "OpenCode": "oc",
    "MimoCode": "mimo",
    "Antigravity": "antigravity_ide",
    # WorkBuddy 自身：作为完成通知智能匹配的自测载体（AUMID 实测自 wpndatabase.db）
    "WorkBuddy.WorkBuddy": "workbuddy",
}

# ---- 完成通知智能匹配（基于 wpndatabase.db 实测真实样本）----
# 真实样本：
#   WorkBuddy : title="任务已完成" body="任务已成功完成。您可以在编辑器中查看结果。"
#   Trae 完成 : title="任务完成"  body="'<task>' 已完成"
#   Trae 失败 : title="异常打断"  body="'<task>' 失败了"
#   MiniMax   : body="等待你的确认"（等待用户输入，并非完成）
#   Codex 空通知: texts=[]（中间态，并非完成）
# 旧实现 _is_task_done_notification 直接 return True，会把 Trae 失败 / MiniMax 等待 / 空通知
# 一律误判为完成。这里改为保守匹配：只在明确是完成类时返回 True。

# 标题中出现即视为完成（短标题是状态标签，可靠）
_COMPLETION_TITLE_KEYWORDS = (
    "任务已完成", "任务完成", "已完成",
    "completed", "finished", "done", "complete",
)

# 正文中的强完成短语（针对标题是任务名而非状态标签的 IDE，如 Codex）
# 注意：单独的「完成」二字在正文里太常见（"我完成了第一步"），不作为正文信号。
_COMPLETION_BODY_PHRASES = (
    "已成功完成", "已经完成", "已完成并", "已完成：",
    "已修改", "已提交", "已重启生效", "已修复", "已实现",
    "completed", "finished",
)

# 负向关键词：出现即视为「非完成」（失败 / 等待 / 错误 / 更新 / 中断），
# 即便同时命中完成关键词也以负向为准，避免误判污染 pending_test 队列。
_NEGATIVE_KEYWORDS = (
    "异常打断", "异常", "中断", "失败", "出错", "错误",
    "error", "failed", "failure", "aborted", "crash",
    "等待你的确认", "等待确认", "需确认", "等待你", "waiting",
    "有新版本", "更新可用", "update available", "新消息", "new message",
)


def classify_completion(title, body):
    """根据通知标题/正文判断是否为「任务完成」类通知。

    保守策略：明确完成 → True；失败/等待/错误/更新/空 → False；模糊 → False。
    非完成类通知仍会经 _process_notification 转发到手机（ide.notification），
    只是不再触发自动 mark_task_done。
    """
    t = (title or "").strip()
    b = (body or "").strip()
    if not t and not b:
        return False
    combined = f"{t} {b}".lower()
    # 负向优先：失败 / 等待 / 错误 / 更新 一律不当完成
    for neg in _NEGATIVE_KEYWORDS:
        if neg.lower() in combined:
            return False
    # 标题命中完成关键词（最可靠）
    tl = t.lower()
    for kw in _COMPLETION_TITLE_KEYWORDS:
        if kw.lower() in tl:
            return True
    # 正文命中强完成短语，且不含问号（避免把"已完成 X，是否继续？"当完成）
    if "?" not in combined and "？" not in combined:
        for kw in _COMPLETION_BODY_PHRASES:
            if kw.lower() in combined:
                return True
    return False

# 通知数据库路径
def _get_wpndb_path():
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return None
    return Path(local_appdata) / "Microsoft" / "Windows" / "Notifications" / "wpndatabase.db"

# 配置文件路径
CONFIG_PATH = Path(__file__).parent / "notification_watcher_config.json"
STATE_PATH = Path(__file__).parent / "notification_watcher_state.json"


def _load_config():
    """加载 AUMID 映射配置"""
    defaults = {"aumid_map": DEFAULT_AUMID_MAP, "poll_interval": 2.0}
    cfg = safe_read_json(CONFIG_PATH, default={})
    if cfg:
        defaults["aumid_map"].update(cfg.get("aumid_map", {}))
        if "poll_interval" in cfg:
            defaults["poll_interval"] = cfg["poll_interval"]
    return defaults


def _load_state():
    """加载水位线状态"""
    return safe_read_json(STATE_PATH, default={"last_order": 0, "seen_ids": []})


def _save_state(state):
    """保存水位线状态"""
    safe_write_json(STATE_PATH, state, indent=None)


def _filetime_to_datetime(filetime):
    """Windows FILETIME (100ns since 1601) 转 datetime"""
    try:
        return datetime(1601, 1, 1) + timedelta(microseconds=filetime / 10)
    except Exception:
        return datetime.now()


def _parse_payload(payload_bytes):
    """解析 Toast XML，提取文本内容"""
    if not payload_bytes:
        return {"title": "", "body": "", "texts": []}
    try:
        text = payload_bytes.decode("utf-8", errors="replace")
        root = ET.fromstring(text)
        texts = []
        # 提取所有 <text> 元素
        for elem in root.iter("{*}text"):
            if elem.text:
                texts.append(elem.text.strip())
        # 兼容无命名空间的情况
        if not texts:
            for elem in root.iter("text"):
                if elem.text:
                    texts.append(elem.text.strip())
        title = texts[0] if texts else ""
        body = " ".join(texts[1:]) if len(texts) > 1 else ""
        return {"title": title, "body": body, "texts": texts, "raw_xml": text}
    except Exception as e:
        return {"title": "", "body": "", "texts": [], "raw_xml": "", "error": str(e)}


def _snapshot_db(db_path):
    """复制数据库副本（避免 WAL 锁），返回临时文件路径"""
    tmp_dir = Path(tempfile.gettempdir())
    tmp_db = tmp_dir / "aidelink_wpndb_snapshot.db"
    tmp_wal = tmp_dir / "aidelink_wpndb_snapshot.db-wal"
    tmp_shm = tmp_dir / "aidelink_wpndb_snapshot.db-shm"

    files_to_copy = [
        (db_path, tmp_db),
        (db_path.parent / "wpndatabase.db-wal", tmp_wal),
        (db_path.parent / "wpndatabase.db-shm", tmp_shm),
    ]

    for src, dst in files_to_copy:
        try:
            if src.exists():
                shutil.copy2(src, dst)
        except Exception:
            pass  # WAL/SHM 可能不存在

    return tmp_db


def _query_new_notifications(tmp_db, last_order):
    """查询新通知，返回 (notifications, max_order)"""
    notifications = []
    max_order = last_order
    try:
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 先查 NotificationHandler 表建立 HandlerId -> AUMID 映射
        handler_map = {}
        try:
            cursor.execute("SELECT RecordId, PrimaryId FROM NotificationHandler")
            for row in cursor.fetchall():
                handler_map[row["RecordId"]] = row["PrimaryId"]
        except Exception:
            pass

        # 查询新通知
        cursor.execute(
            'SELECT "Order", "Id", "HandlerId", "Type", "ArrivalTime", "Payload", "Tag" '
            "FROM Notification WHERE \"Order\" > ? ORDER BY \"Order\"",
            (last_order,),
        )
        for row in cursor.fetchall():
            order = row["Order"]
            if order > max_order:
                max_order = order
            handler_id = row["HandlerId"]
            aumid = handler_map.get(handler_id, "")
            payload = row["Payload"]
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            parsed = _parse_payload(payload)
            arrival = _filetime_to_datetime(row["ArrivalTime"] or 0)
            notifications.append({
                "order": order,
                "notification_id": row["Id"],
                "handler_id": handler_id,
                "aumid": aumid,
                "type": row["Type"],
                "arrival_time": arrival.isoformat(timespec="seconds"),
                "tag": row["Tag"],
                "title": parsed["title"],
                "body": parsed["body"],
                "texts": parsed["texts"],
                "raw_xml": parsed.get("raw_xml", ""),
            })

        conn.close()
    except sqlite3.OperationalError:
        pass  # 数据库锁或损坏，跳过本轮
    except Exception:
        pass

    return notifications, max_order


def _bring_ide_to_foreground(ide_key):
    """把指定 IDE 窗口拉到前台（任务完成后让用户看结果）。仅 Windows。

    用于浮窗派发的任务：完成时用户在电脑前（浮窗前台），把刚完成的 IDE 拉到前台方便看结果。
    远程派发（安卓/Web/MCP）用户不在电脑前，调用方应已跳过。
    """
    if os.name != "nt" or not ide_key:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        from window_binding import find_bound_window
        win = find_bound_window(ide_key)
        if not win:
            return
        hwnd = int(getattr(win, "_hWnd", 0) or 0)
        if not hwnd:
            return
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        cur_tid = kernel32.GetCurrentThreadId()
        attached = False
        if fg_tid and fg_tid != cur_tid:
            attached = user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
    except Exception:
        pass


class NotificationWatcher:
    """Windows 通知监控器"""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self._thread = None
        self._stop_event = threading.Event()
        self._config = _load_config()
        self._state = _load_state()
        self._db_path = _get_wpndb_path()
        self._last_check = None
        self._idle_samples = {}  # CPU 空闲采样计数 {ide_key: count}
        self._last_db_mtime = 0
        self._last_wal_mtime = 0

    def _match_ide(self, aumid):
        """根据 AUMID 匹配 IDE，返回 ide key 或 None。

        匹配策略（避免 Trae 多系列串台）：
        1. 精确匹配（大小写不敏感）—— AUMID 是精确标识，优先精确。
           旧实现用双向子串 `a in b or b in a`，会把 "ByteDance.Trae" 当成
           "ByteDance.TraeSoloCN" 的子串而误归 trae_solo_cn，造成系列串台。
        2. 前缀+分隔符匹配：处理带后缀的 AUMID（如 OpenAI.Codex_xxx!App），
           仅当前缀后紧跟 ! . _ 或到结尾时才算命中，避免 Trae 误命中 TraeSoloCN。
        """
        if not aumid:
            return None
        aumid_lower = aumid.lower()
        am = self._config["aumid_map"]
        # 1) 精确匹配
        for mapped_aumid, ide_key in am.items():
            if mapped_aumid.lower() == aumid_lower:
                return ide_key
        # 2) 前缀 + 分隔符匹配
        for mapped_aumid, ide_key in am.items():
            m = mapped_aumid.lower()
            if aumid_lower.startswith(m) and (
                len(aumid_lower) == len(m) or aumid_lower[len(m)] in "!._"
            ):
                return ide_key
        return None

    def _is_task_done_notification(self, notif):
        """判断该通知是否为「任务完成」类（委托给模块级 classify_completion）。

        旧实现直接 return True，会把 Trae 的「异常打断/失败」、MiniMax 的「等待你的确认」、
        Codex 的空通知等一律误判为完成并自动 mark_task_done。改为基于真实通知文本的保守匹配：
        只有明确是完成类才返回 True，其余仍转发到手机但不自动落 pending_test。
        """
        return classify_completion(notif.get("title", ""), notif.get("body", ""))

    def _is_task_recently_started(self, ide_key, min_seconds=60):
        """检查该 IDE 当前任务是否刚启动（已废弃此抑制逻辑以防止丢失通知）"""
        return False

    def _process_notification(self, notif):
        """处理单条通知，发布事件"""
        ide_key = self._match_ide(notif["aumid"])
        if not ide_key:
            text_to_check = f"{notif.get('title', '')} {notif.get('body', '')}".lower()
            if "antigravity" in text_to_check or "antigravity_ide" in text_to_check:
                ide_key = "antigravity_ide"
            else:
                ide_key = "PC"

        is_task_done = self._is_task_done_notification(notif)

        event_data = {
            "ide": ide_key,
            "aumid": notif["aumid"],
            "title": notif["title"],
            "body": notif["body"],
            "arrival_time": notif["arrival_time"],
            "is_task_done": is_task_done,
            "notification_id": notif["notification_id"],
        }

        if self.event_bus:
            self.event_bus.publish("ide.notification", event_data)
            if is_task_done:
                self.event_bus.publish("ide.task_done", event_data)
                # 自动更新任务状态为 pending_test
                self._auto_update_task_status(ide_key)

        print(f"[NotificationWatcher] ide={ide_key} title={notif['title']!r} "
              f"body={notif['body']!r} task_done={is_task_done}", flush=True)

    def _auto_update_task_status(self, ide_key):
        """检测到 IDE 完成任务后，自动将当前运行任务标记为 pending_test。

        注意：调用方 _process_notification 已通过 _is_task_recently_started 抑制了
        派发时的误触，此处无需重复检查时间窗口。
        """
        try:
            import os
            from pathlib import Path
            base_dir = Path(__file__).parent
            ide_status_file = base_dir / "state" / "ide_status.json"
            ide_status = safe_read_json(ide_status_file, default={})
            if not ide_status:
                return
            current_task_id = ide_status.get(ide_key, {}).get("current_task_id")
            if not current_task_id:
                return
            from task_runtime import TaskRuntime
            rt = TaskRuntime(str(base_dir))
            task = rt.get_task(current_task_id)
            if task and task.get("status") == "running":
                rt.mark_task_done(current_task_id, summary="IDE 报告任务完成")
                print(f"[NotificationWatcher] Auto-marked task {current_task_id} as pending_test", flush=True)
                # 完成后若任务是浮窗派发的（用户在电脑前），把对应 IDE 拉到前台看结果
                try:
                    _src = (task.get("metadata") or {}).get("created_from") or task.get("source") or ""
                    if _src == "floating_window":
                        _bring_ide_to_foreground(ide_key)
                except Exception:
                    pass
        except Exception as e:
            print(f"[NotificationWatcher] Failed to auto-update task status: {e}", flush=True)

    def _check_cli_ide_completion(self):
        """检查 CLI IDE（mimo/oc/oc_web）是否完成了任务。

        检测优先级（按可靠性排序）：
        1. Session API 轮询所有 Web / Serve 会话（支持手动对话和官方 Web 页面的推送）
        2. CPU 活跃度检测（交互模式，最后手段）
        """
        try:
            import os
            from pathlib import Path
            from task_runtime import TaskRuntime
            base_dir = Path(__file__).parent
            rt = TaskRuntime(str(base_dir))
            ide_status = rt.read_ide_status()
            tasks = rt.read_tasks()
            
            # 1. 轮询所有 Web / Serve 会话（支持手动对话和官方 Web 页面的推送）
            self._check_all_sessions_completion()

            # 2. 如果任务仍为 running 且非 serve 模式，使用 CPU 活跃度检测（交互模式）
            if ide_status and tasks:
                cli_ides = ("mimo", "oc")
                for ide_key in cli_ides:
                    status_info = ide_status.get(ide_key, {})
                    current_task_id = status_info.get("current_task_id")
                    if not current_task_id:
                        continue

                    task = next((t for t in tasks if t.get("task_id") == current_task_id), None)
                    if not task or task.get("status") != "running":
                        continue

                    self._check_cpu_idle_completion(ide_key, current_task_id, base_dir)

        except Exception as e:
            print(f"[NotificationWatcher] CLI completion check error: {e}", flush=True)

    # CLI serve IDE 的端口映射
    CLI_SERVE_PORTS = {"mimo": 4097, "oc": 4096}

    def _check_all_sessions_completion(self):
        """轮询所有活动的 Web / CLI Serve IDE 会话，检测新完成 of AI 回复并推送通知"""
        import requests
        from pathlib import Path
        from task_runtime import TaskRuntime
        base_dir = Path(__file__).parent
        
        # 获取当前运行的任务状态
        rt = TaskRuntime(str(base_dir))
        ide_status = rt.read_ide_status()
        tasks = rt.read_tasks()
        
        # 端口映射: {port: ide_key}
        # 4096: oc / oc_web (OpenCode web / CLI)
        # 4097: mimo (Mimo CLI)
        ports = {4096: "oc_web", 4097: "mimo"}
        
        # 从 state 中获取已通知的消息记录
        # 格式: {"session_id": "last_msg_id_or_hash"}
        notified_msgs = self._state.setdefault("notified_web_messages", {})
        
        state_changed = False
        for port, ide_key in ports.items():
            oc_base = f"http://127.0.0.1:{port}"
            try:
                sessions_resp = requests.get(f"{oc_base}/session", timeout=2)
                if sessions_resp.status_code != 200:
                    continue
                
                sessions = sessions_resp.json()
                if not sessions:
                    continue
                
                for s in sessions:
                    session_id = s.get("id")
                    session_title = s.get("title", "未命名会话")
                    if not session_id:
                        continue
                    
                    msg_resp = requests.get(f"{oc_base}/session/{session_id}/message", timeout=3)
                    if msg_resp.status_code != 200:
                        continue
                    
                    messages = msg_resp.json()
                    if not messages:
                        continue
                    
                    # 找到最后一个 assistant 消息
                    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
                    if not assistant_msgs:
                        continue
                    
                    last_asst = assistant_msgs[-1]
                    # 获取消息 ID
                    msg_id = last_asst.get("id")
                    
                    # 提取文本内容
                    parts = last_asst.get("parts", [])
                    result_text = ""
                    for part in parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            result_text += part.get("text", "")
                        elif isinstance(part, str):
                            result_text += part
                    
                    result_text = result_text.strip()
                    if not result_text:
                        continue
                    
                    # 如果消息没有 id，使用内容 hash 作为唯一标识
                    if not msg_id:
                        import hashlib
                        msg_id = hashlib.md5(result_text.encode('utf-8')).hexdigest()
                    
                    # 检查是否已经通知过
                    if notified_msgs.get(session_id) == msg_id:
                        continue
                    
                    # 检查是否完成
                    metadata = last_asst.get("metadata", {})
                    is_complete = metadata.get("finish", "") in ("end-turn", "stop", "tool-result")
                    
                    # 兜底时间检查
                    if not is_complete and len(messages) >= 2:
                        last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
                        if last_user:
                            last_user_time = last_user.get("metadata", {}).get("time", {})
                            last_asst_time = metadata.get("time", {})
                            user_end = last_user_time.get("end", 0)
                            asst_end = last_asst_time.get("end", 0)
                            if asst_end > 0 and user_end > 0 and asst_end > user_end:
                                is_complete = True
                                
                    if is_complete:
                        # 记录已通知
                        notified_msgs[session_id] = msg_id
                        state_changed = True
                        
                        # 准备推送事件
                        preview = result_text[:150] + ("..." if len(result_text) > 150 else "")
                        # 决定显示的 IDE 名称
                        display_name = "OpenCode Web" if port == 4096 else "Mimo CLI"
                        
                        event_data = {
                            "ide": ide_key,
                            "title": f"🔔 {display_name}: {session_title}",
                            "body": preview,
                            "summary": preview,
                            "arrival_time": datetime.now().isoformat(),
                            "is_task_done": True,
                        }
                        
                        if self.event_bus:
                            # 发送事件到 EventBus，触发 App 侧的高优先级铃声通知
                            self.event_bus.publish("ide.task_done", event_data)
                            self.event_bus.publish("task.pending_test", event_data)
                            print(f"[NotificationWatcher] Pushed notification for web session {session_id} on port {port}", flush=True)
                        
                        # 联动更新 tasks.json 中的任务状态 (如果是 AideLink 派发的任务)
                        current_task_id = ide_status.get(ide_key, {}).get("current_task_id")
                        task = None
                        if current_task_id:
                            task = next((t for t in tasks if t.get("task_id") == current_task_id), None)
                        
                        if not task:
                            # 尝试通过标题匹配
                            task = next((t for t in tasks if t.get("status") == "running" and t.get("target_ide") == ide_key and t.get("title", "")[:15] in session_title), None)
                            
                        if task and task.get("status") == "running":
                            from task_runtime import TaskRuntime
                            rt = TaskRuntime(str(base_dir))
                            rt.update_task(task["task_id"], result=result_text)
                            rt.mark_task_done(task["task_id"], summary=preview)
                            print(f"[NotificationWatcher] Auto-updated task {task['task_id']} to pending_test", flush=True)
                            
            except requests.ConnectionError:
                pass
            except Exception as e:
                print(f"[NotificationWatcher] Session check error on port {port}: {e}", flush=True)
                
        if state_changed:
            self._state["notified_web_messages"] = notified_msgs
            _save_state(self._state)

    def _check_cpu_idle_completion(self, ide_key, task_id, base_dir):
        """通过 CPU 使用率检测 CLI IDE（交互模式）是否完成任务。

        当 IDE 工作时 CPU > 10%（思考/调用工具/读写文件），
        回到交互提示符后 CPU < 1%。连续 3 次空闲采样才确认。
        """
        try:
            import psutil
            found = False
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                name = (proc.info.get("name") or "").lower()
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                if ide_key not in name and ide_key not in cmdline:
                    continue
                # 排除 bridge 自身的进程（通过 parent pid 或 cmdline 过滤）
                try:
                    p = psutil.Process(proc.info["pid"])
                    # 跳过 bridge 主进程的子进程
                    if p.parent() and p.parent().pid == os.getpid():
                        continue
                except Exception:
                    pass

                found = True
                try:
                    cpu = proc.info["pid"] and psutil.Process(proc.info["pid"]).cpu_percent(interval=0.3)
                except Exception:
                    cpu = 0

                if cpu is not None and cpu < 1.0:
                    self._idle_samples[ide_key] = self._idle_samples.get(ide_key, 0) + 1
                    if self._idle_samples[ide_key] >= 3:
                        from task_runtime import TaskRuntime
                        rt = TaskRuntime(str(base_dir))
                        rt.mark_task_done(task_id, summary=f"CLI IDE 任务完成（CPU 空闲检测，{ide_key}）")
                        print(f"[NotificationWatcher] CLI {ide_key}: task {task_id} done (CPU idle x3)", flush=True)
                        self._idle_samples[ide_key] = 0
                        return True
                else:
                    self._idle_samples[ide_key] = 0
                break  # 只检查第一个匹配的进程

            if not found:
                # 进程不存在，可能已退出
                self._idle_samples.pop(ide_key, None)
            return False
        except ImportError:
            return False  # psutil 未安装
        except Exception as e:
            print(f"[NotificationWatcher] CPU idle check for {ide_key} error: {e}", flush=True)
            return False
    def _poll_loop(self):
        """轮询主循环"""
        poll_interval = self._config.get("poll_interval", 2.0)
        print(f"[NotificationWatcher] Started, db={self._db_path}, "
              f"interval={poll_interval}s", flush=True)

        cli_check_counter = 0
        while not self._stop_event.is_set():
            try:
                if self._db_path and self._db_path.exists():
                    db_mtime = os.path.getmtime(self._db_path)
                    wal_path = self._db_path.parent / "wpndatabase.db-wal"
                    wal_mtime = os.path.getmtime(wal_path) if wal_path.exists() else 0

                    if db_mtime != self._last_db_mtime or wal_mtime != self._last_wal_mtime:
                        self._last_db_mtime = db_mtime
                        self._last_wal_mtime = wal_mtime

                        tmp_db = _snapshot_db(self._db_path)
                        notifications, max_order = _query_new_notifications(
                            tmp_db, self._state.get("last_order", 0)
                        )

                        for notif in notifications:
                            self._process_notification(notif)

                        if max_order > self._state.get("last_order", 0):
                            self._state["last_order"] = max_order
                            self._state["seen_ids"] = self._state.get("seen_ids", [])[-500:]
                            _save_state(self._state)

                        # 清理临时文件
                        try:
                            tmp_db.unlink(missing_ok=True)
                        except Exception:
                            pass

                    self._last_check = datetime.now().isoformat(timespec="seconds")
                else:
                    self._last_check = datetime.now().isoformat(timespec="seconds")

                # 每 10 秒检查一次 CLI IDE（mimo/oc）任务完成
                cli_check_counter += 1
                if cli_check_counter >= max(1, int(10 / poll_interval)):
                    cli_check_counter = 0
                    self._check_cli_ide_completion()
            except Exception as e:
                print(f"[NotificationWatcher] Error: {e}", flush=True)

            self._stop_event.wait(poll_interval)

        print("[NotificationWatcher] Stopped", flush=True)

    def start(self):
        """启动监控线程"""
        if self._thread and self._thread.is_alive():
            return
        if not self._db_path or not self._db_path.exists():
            print("[NotificationWatcher] wpndatabase.db not found, not starting", flush=True)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="NotificationWatcher")
        self._thread.start()

    def stop(self):
        """停止监控线程"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def get_status(self):
        """获取监控状态"""
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "db_path": str(self._db_path) if self._db_path else None,
            "last_order": self._state.get("last_order", 0),
            "last_check": self._last_check,
            "aumid_map": self._config.get("aumid_map", {}),
            "poll_interval": self._config.get("poll_interval", 2.0),
        }

    def list_known_aumids(self):
        """列出数据库中所有已知的通知发起者（用于配置 AUMID 映射）"""
        if not self._db_path or not self._db_path.exists():
            return []
        tmp_db = _snapshot_db(self._db_path)
        handlers = []
        try:
            conn = sqlite3.connect(str(tmp_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT RecordId, PrimaryId, CreatedTime FROM NotificationHandler")
            for row in cursor.fetchall():
                handlers.append({
                    "record_id": row["RecordId"],
                    "aumid": row["PrimaryId"],
                    "created_time": _filetime_to_datetime(row["CreatedTime"] or 0).isoformat(timespec="seconds"),
                    "mapped_ide": self._match_ide(row["PrimaryId"]),
                })
            conn.close()
        except Exception:
            pass
        try:
            tmp_db.unlink(missing_ok=True)
        except Exception:
            pass
        return handlers

    def update_aumid_map(self, aumid, ide_key):
        """更新 AUMID 映射"""
        self._config["aumid_map"][aumid] = ide_key
        safe_write_json(CONFIG_PATH, {"aumid_map": self._config["aumid_map"],
                                      "poll_interval": self._config["poll_interval"]})


# 全局单例
_watcher = None


def get_watcher(event_bus=None):
    global _watcher
    if _watcher is None and event_bus is not None:
        _watcher = NotificationWatcher(event_bus)
    return _watcher
