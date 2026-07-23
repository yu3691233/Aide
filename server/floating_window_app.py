import ctypes
from ctypes import wintypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from floating_icons import IconFactory

import io

from PIL import Image, ImageDraw, ImageTk, ImageFont


def _set_window_rect(hwnd, x, y, w, h):
    """用 SetWindowPos 把窗口精确摆到虚拟屏坐标（支持负坐标，绕过 Tk geometry 的限制）。"""
    try:
        user32 = ctypes.windll.user32
        SWP_NOACTIVATE = 0x10
        SWP_SHOWWINDOW = 0x40
        user32.SetWindowPos(int(hwnd), -1, int(x), int(y), int(w), int(h),
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        pass


def _fetch_monitors():
    """从 AideLink 桥接服务获取显示器列表（复用 /screenshot/monitors）。

    显示器枚举与截图都放在「服务器进程」里完成——服务器进程已正确开启 DPI 感知，
    多屏截图稳定；本进程保持非 DPI 感知（否则浮窗 UI 会缩小），只负责 UI。

    返回 (monitors, err)：monitors 为
    [{name, rect:(设备像素 l,t,r,b), primary:bool, scale_factor:float}, ...]，
    按主屏优先、左边界排序；err 为错误信息字符串（成功时 None）。
    """
    try:
        data = api_request("screenshot/monitors", timeout=5)
    except Exception as exc:
        return None, f"无法连接截图服务：{exc}"
    if not isinstance(data, dict) or not data.get("ok"):
        err = data.get("error") if isinstance(data, dict) else str(data)
        return None, f"截图服务返回异常：{err}"
    raw = data.get("monitors") or []
    monitors = []
    for m in raw:
        left, top, right, bottom = m.get("left"), m.get("top"), m.get("right"), m.get("bottom")
        if right is None or bottom is None or right <= left or bottom <= top:
            continue
        monitors.append({
            "name": m.get("name") or "primary",
            "rect": (int(left), int(top), int(right), int(bottom)),
            "primary": bool(m.get("primary")),
            "scale_factor": float(m.get("scale_factor") or 1.0),
        })
    if not monitors:
        return None, "未检测到显示器"
    monitors.sort(key=lambda m: (0 if m["primary"] else 1, m["rect"][0]))
    return monitors, None
BRIDGE_URL = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000")
BOOTSTRAP_URL = f"{BRIDGE_URL.rstrip('/')}/api/floating-window/bootstrap"
WINDOW_MUTEX_NAME = "Local\\AideLinkFloatingWindow"
WINDOW_TITLE_FALLBACK = "暂无项目"
WINDOW_WIDTH = 370
SHOW_SIGNAL_PORT = int(os.environ.get("AIDELINK_FLOATING_WINDOW_PORT", "51231"))
VISIBLE_TASK_ACTIONS = ("copy", "view", "more")
DEFAULT_QUICK_REPLIES = ("继续", "安装到手机", "升级版本号并提交git")
DEFAULT_COLLAPSED_GROUPS = frozenset({"待测试", "已完成"})
TEST_FEEDBACK_MARKER = "\n\n---\n测试反馈："
INPUT_HINT = "描述任务目标，或粘贴生成后的提示词…"
PROMPT_TASK_TYPES = (
    ("unspecified", "未指定"),
    ("feature", "新增功能"),
    ("optimize", "功能优化"),
    ("ui", "界面优化"),
    ("bug", "修复bug"),
)
PROMPT_CATEGORY_TO_COMPOSE_TYPE = {
    "unspecified": "auto",
    "feature": "feature_change",
    "optimize": "feature_change",
    "ui": "feature_change",
    "bug": "bug_fix",
}
PROMPT_CATEGORY_TO_CLASSIFICATION_TYPE = {
    "feature": "feature",
    "optimize": "optimization",
    "ui": "optimization",
    "bug": "bug_fix",
}
QUICK_REPLIES_FILE = Path(__file__).resolve().parent / "state" / "floating_quick_replies.json"
WINDOW_STATE_FILE = Path(__file__).resolve().parent / "state" / "floating_window_state.json"
# 记录浮窗启动时获取 Codex 额度的时间戳，10 分钟内重启不重复获取。
QUOTA_LAST_FETCH_FILE = Path(__file__).resolve().parent / "state" / "floating_window_quota_last_fetch.json"
QUOTA_STARTUP_FETCH_INTERVAL = 600
PLATFORM_SPECS = (
    ("android", "smartphone", "#35a853", "Android"),
    ("web", "globe", "#0867f2", "Web"),
    ("windows", "windows", "#0867f2", "Windows"),
)


def _project_name(project):
    if not project:
        return WINDOW_TITLE_FALLBACK
    name = str(project.get("name") or "").strip()
    if name:
        return name
    path = str(project.get("path") or "").strip().rstrip("\\/")
    return os.path.basename(path) if path else WINDOW_TITLE_FALLBACK


def _capability_badge(capabilities):
    capabilities = {str(item).lower() for item in (capabilities or [])}
    return (
        ("📱" if "android" in capabilities else "")
        + ("🌐" if "web" in capabilities else "")
        + ("🖥" if "windows" in capabilities else "")
    )


def _project_platforms(capabilities):
    available = {str(item).strip().lower() for item in (capabilities or [])}
    return [key for key, _icon, _color, _label in PLATFORM_SPECS if key in available]


def _task_surface(task, project_capabilities):
    metadata = task.get("metadata") or {}
    component = metadata.get("component") or {}
    hints = " ".join(str(value) for value in (
        task.get("surface"),
        task.get("platform"),
        metadata.get("surface"),
        metadata.get("platform"),
        component.get("platform"),
        task.get("title"),
    ) if value).lower()
    if "android" in hints or "apk" in hints or "app" in hints:
        return "android"
    if "web" in hints or "网页" in hints or "页面" in hints or "browser" in hints:
        return "web"
    capabilities = {str(item).lower() for item in (project_capabilities or [])}
    if capabilities == {"android"}:
        return "android"
    if capabilities == {"web"}:
        return "web"
    return "general"


def _status_label(status):
    return {
        "pending_test": "待测试",
        "test_failed": "待修复",
        "merge_conflict": "冲突",
        "running": "执行中",
        "dispatched": "已派发",
        "queued": "排队中",
        "draft": "待派发",
        "pending": "待派发",
        "failed": "失败",
        "timeout": "超时",
        "done": "已完成",
        "completed": "已完成",
    }.get(status or "", status or "未知")


def _task_group_name(task):
    status = task.get("status") or ""
    if status == "已完成":
        return "已完成"
    if status in {"待测试", "超时"}:
        return "待测试"
    if status in {"执行中", "已派发", "排队中"}:
        return "进行中"
    return "待派发"


def _task_test_result(task):
    status = _status_label(task.get("status") or "")
    if status not in {"待测试", "超时"}:
        return ""
    result = str(task.get("test_result") or "").strip().lower()
    return result if result in {"queued", "dispatched", "passed", "failed"} else ""


def _latest_task_id(tasks):
    if not tasks:
        return None
    return max(
        tasks,
        key=lambda task: str(task.get("updated_at") or task.get("created_at") or ""),
    ).get("task_id")


def _task_title(task):
    title = str(task.get("title") or "").strip()
    if title and not title.lower().startswith("<think>"):
        return title
    return task.get("text") or task.get("message") or task.get("task_id") or "无标题任务"


def _clean_task_text(value):
    text = str(value or "")
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^<think>.*?(?=\n\n|$)", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"```(?:\w+)?|```", " ", text)
    text = re.sub(r"\bThe user (?:is asking|wants).*?(?=\n|$)", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def task_copy_text(task):
    title = _clean_task_text(task.get("title"))
    body = _clean_task_text(task.get("text") or task.get("message"))
    parts = [part for part in (title, body) if part]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts.pop()
    return "\n\n".join(parts) or "无标题任务"


def choose_selected_ide(current_key, ides, preferred_key=None):
    # Busy is a status hint, not a selection lock. A running IDE remains a
    # valid target for the next direct message.
    available = [ide for ide in ides if ide.get("running")]
    keys = {ide.get("key") for ide in available}
    if current_key in keys:
        return current_key
    if preferred_key in keys:
        return preferred_key
    return available[0].get("key") if available else None


def build_home_model(payload):
    payload = payload or {}
    project = payload.get("project") or {}
    ides = payload.get("ides") or []
    summary = payload.get("task_summary") or {}
    tasks = payload.get("tasks") or []
    selected = payload.get("selected_target") or {}

    by_status = summary.get("by_status") or {}
    pending_test = int(by_status.get("pending_test") or 0) + int(by_status.get("timeout") or 0)
    running = int(by_status.get("running") or 0) + int(by_status.get("dispatched") or 0) + int(by_status.get("queued") or 0)
    pending_dispatch = sum(int(by_status.get(status) or 0) for status in ("draft", "pending", "failed", "test_failed", "merge_conflict"))
    completed = int(by_status.get("done") or 0) + int(by_status.get("completed") or 0)

    capabilities = payload.get("capabilities") or project.get("capabilities") or ["general"]
    project_name = _project_name(project)
    badge = _capability_badge(capabilities)

    return {
        "title": f"{project_name} {badge}".strip(),
        "project_name": _project_name(project),
        "project_path": project.get("path") or "",
        "capabilities": capabilities,
        "ides": [
            {
                "key": ide.get("key", ""),
                "name": ide.get("name") or ide.get("key") or "IDE",
                "running": bool(ide.get("running")),
                "busy": bool(ide.get("busy")),
                "dispatchable": bool(ide.get("dispatchable", ide.get("running"))),
                "dot": "🟡" if ide.get("busy") else ("●" if ide.get("running") else "○"),
                "current_task_id": ide.get("current_task_id"),
                "path": ide.get("path") or "",
            }
            for ide in ides
        ],
        "selected_target": selected.get("name") or selected.get("key") or "未选择 IDE",
        "selected_target_key": selected.get("key"),
        "summary": {
            "待派发": pending_dispatch,
            "待测试": pending_test,
            "进行中": running,
            "已完成": completed,
        },
        "tasks": [
            {
                "title": _clean_task_text(_task_title(task)) or "无标题任务",
                "text": task.get("text") or task.get("message") or "",
                "task_id": task.get("task_id") or "",
                "status": _status_label(task.get("status")),
                "target_ide": task.get("target_ide") or "未分配",
                "surface": _task_surface(task, capabilities),
                "progress": int(task.get("progress") or (task.get("metadata") or {}).get("progress") or 0),
                "allowed_actions": list(task.get("allowed_actions") or ["view"]),
                "feedbacks": list(task.get("feedbacks") or (task.get("metadata") or {}).get("feedbacks") or []),
                "summary": task.get("summary") or "",
                "error": task.get("error") or "",
                "updated_at": task.get("updated_at") or task.get("created_at") or "",
                "content_kind": (task.get("metadata") or {}).get("content_kind") or "task",
                "version": task.get("app_version") or task.get("version") or task.get("git_version") or "",
            }
            for task in tasks
        ],
    }


def fetch_bootstrap(timeout=3):
    with urlopen(BOOTSTRAP_URL, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def api_request(path, method="GET", payload=None, timeout=15):
    url = f"{BRIDGE_URL.rstrip('/')}/{path.lstrip('/')}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"message": raw or str(exc)}
        result.setdefault("ok", False)
        result.setdefault("status", exc.code)
        return result


def http_get_bytes(url, timeout=15):
    """下载二进制数据（如截图字节）。失败返回 None。"""
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def http_post_multipart(url, fields=None, files=None, timeout=30):
    """上传 multipart/form-data（用于 /upload 接口）。
    fields: dict[str, str]；files: dict[field_name, (filename, bytes, content_type)]。
    """
    boundary = "----AideLinkFloatingWindow" + str(int(time.time() * 1000))
    parts = []
    for name, value in (fields or {}).items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        parts.append(f"{value}\r\n".encode("utf-8"))
    for field_name, (filename, data, content_type) in (files or {}).items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'.encode("utf-8")
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = Request(
        url,
        data=b"".join(parts),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"message": raw or str(exc)}
        result.setdefault("ok", False)
        result.setdefault("status", exc.code)
        return result
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "message": str(exc)}


class SingleInstance:
    def __init__(self, name=WINDOW_MUTEX_NAME):
        self.name = name
        self.handle = None

    def acquire(self):
        if os.name != "nt":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            return True
        return ctypes.get_last_error() != 183

    def release(self):
        if os.name == "nt" and self.handle:
            try:
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            finally:
                self.handle = None


@dataclass
class RefreshResult:
    ok: bool
    model: dict
    error: str = ""


class FloatingWindowApp:
    def __init__(self, refresh_seconds=7):
        import tkinter as tk

        self.tk = tk
        self.refresh_seconds = refresh_seconds
        self.drag_start = (0, 0)
        self.drag_moved = False
        self.is_topmost = True
        self.selected_ide_key = None
        self.selected_surface = None
        self.surface_project_key = None
        self.active_tab = "create"
        self.prompt_task_type = "unspecified"
        self.prompt_component_name = ""
        self.prompt_component_location = ""
        self.prompt_component_ref = {}
        self.component_pools = {}
        self.prompt_candidates = []
        self.expanded_task_id = None
        self.test_selection_mode = False
        self.selected_test_task_ids = set()
        self.collapsed_groups = set(DEFAULT_COLLAPSED_GROUPS)
        self.completed_display_limit = 5
        self.input_expanded = False
        self.input_expand_after_id = None
        self.input_draft_after_id = None
        self.refresh_in_progress = False
        self.last_render_signature = None
        self.connection_failed = False
        self._startup_quota_done = False
        self.status_detail = ""
        self.ui_callbacks = queue.Queue()
        self.editing_task_id = None
        self.input_draft_before_task_edit = ""
        self.test_feedback_task_id = None
        self.input_draft_before_test_feedback = ""
        self.test_feedback_context = ""
        self.current_model = {}
        self.root = tk.Tk()
        self.icons = IconFactory(self.root)
        self.root.title(WINDOW_TITLE_FALLBACK)
        self.window_width = WINDOW_WIDTH
        self.min_window_height = 500
        self.max_window_height = 720
        default_x, default_y = self._initial_window_position(560)
        initial_height = max(self.min_window_height, min(560, self.max_window_height))
        self.root.geometry(f"{self.window_width}x{initial_height}{default_x:+d}{default_y:+d}")
        self.root.minsize(min(350, self.window_width), self.min_window_height)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#ffffff")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(0, self._enable_rounded_window)
        self._build_ui()
        self._restore_input_draft()
        self.root.after(25, self._drain_ui_callbacks)
        self.refresh()
        self._start_signal_server()
        self._schedule_refresh()

    def _build_ui(self):
        tk = self.tk
        bg = "#ffffff"
        card = "#ffffff"
        border = "#dbe2ea"
        text = "#172033"
        muted = "#657084"
        blue = "#0867f2"

        shell = tk.Frame(self.root, bg=bg, highlightbackground="#dbe2ea", highlightthickness=1)
        shell.pack(fill="both", expand=True)

        self.title_bar = tk.Frame(shell, bg=card, height=40, highlightthickness=0)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)
        self.title_bar.bind("<ButtonPress-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._drag)
        self.title_bar.bind("<ButtonRelease-1>", self._finish_drag)

        project_box = tk.Frame(self.title_bar, bg=card, highlightthickness=0)
        project_box.pack(side="left", padx=8, pady=2)
        self.title_label = tk.Label(project_box, text=WINDOW_TITLE_FALLBACK, fg=text, bg=card, font=("Microsoft YaHei UI", 10, "bold"), anchor="w", padx=4)
        self.title_label.pack(side="left", ipady=7)
        self.title_label.bind("<ButtonPress-1>", self._start_drag)
        self.title_label.bind("<B1-Motion>", self._drag)
        self.title_label.bind("<ButtonRelease-1>", self._open_project_picker)
        tk.Label(project_box, image=self.icons.get("chevron_down", 13), bg=card).pack(side="left", padx=(0, 6))
        tk.Frame(project_box, bg=border, width=1, height=28).pack(side="left", padx=2)
        self.capability_frame = tk.Frame(project_box, bg=card, highlightthickness=0)
        self.capability_frame.pack(side="left", padx=(5, 2))

        self.quota_frame = tk.Frame(self.title_bar, bg=card, highlightthickness=0)
        self.quota_frame.place(relx=0.55, rely=0.5, anchor="center")
        self.quota_prefix = tk.Label(
            self.quota_frame, text="codex", fg="#8a94a6", bg=card,
            font=("Microsoft YaHei UI", 7), width=5, anchor="w",
        )
        self.quota_prefix.pack(side="left", padx=(0, 2))
        self.quota_canvas = tk.Canvas(
            self.quota_frame, width=40, height=8, bg=card, highlightthickness=0
        )
        self.quota_canvas.pack(side="left", padx=(0, 4))
        self.quota_label = tk.Label(
            self.quota_frame, text="--%", fg="#657084", bg=card,
            font=("Microsoft YaHei UI", 8), width=4, anchor="w",
        )
        self.quota_label.pack(side="left")
        for widget in (self.quota_frame, self.quota_prefix, self.quota_canvas, self.quota_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._on_quota_click)

        actions = tk.Frame(self.title_bar, bg=card, highlightthickness=0)
        actions.pack(side="right", padx=5, pady=2)
        self.top_btn = self._icon_button(actions, "pin", self.toggle_topmost, size=16)
        self.top_btn.pack(side="left", padx=1)
        self.close_btn = self._icon_button(actions, "x", self.close, size=16)
        self.close_btn.pack(side="left", padx=1)

        composer = tk.Frame(shell, bg=bg)
        composer.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        ide_row = tk.Frame(composer, bg=bg)
        ide_row.pack(fill="x", pady=(0, 3))
        self.ide_frame = tk.Frame(ide_row, bg=bg)
        self.ide_frame.pack(side="left", fill="x", expand=True)

        self.input_frame = tk.Frame(composer, bg=bg)
        self.input_frame.pack(fill="x")

        input_shell = tk.Canvas(self.input_frame, bg=bg, height=58, highlightthickness=0)
        input_shell.pack(fill="x")
        self.input_shell = input_shell
        self.input_box = tk.Text(input_shell, height=1, wrap="word", relief="flat", bd=0, bg=card, fg=text, insertbackground=text, font=("Microsoft YaHei UI", 9), undo=True, autoseparators=True, maxundo=-1)
        input_window = input_shell.create_window(12, 9, anchor="nw", window=self.input_box)
        self.input_box.insert("1.0", INPUT_HINT)
        self.input_box.edit_reset()
        self.input_box.config(fg="#8a94a6")
        self.input_box.bind("<FocusIn>", self._clear_input_hint)
        self.input_box.bind("<KeyRelease>", self._schedule_auto_expand)
        self.input_box.bind("<Return>", self._handle_input_return)
        self.input_box.bind("<Control-Return>", self._handle_input_ctrl_return)
        self.input_box.bind("<Control-z>", self._handle_input_undo)
        add_image = self.icons.get("plus", 20, "#283246")
        expand_image = self.icons.get("expand", 17, "#657084")
        prompt_image = self.icons.get("bot", 18, "#7757e8")
        send_image = self.icons.get("send", 20, "#0867f2")
        input_shell._action_images = (add_image, expand_image, prompt_image, send_image)
        add_icon_item = input_shell.create_image(22, 40, image=add_image, tags="add-action")
        expand_icon_item = input_shell.create_image(350, 12, image=expand_image, tags="expand-action")
        prompt_icon_item = input_shell.create_image(330, 40, image=prompt_image, tags="prompt-action")
        send_icon_item = input_shell.create_image(368, 40, image=send_image, tags=("send-action", "send-icon"))
        input_shell.tag_bind("add-action", "<Button-1>", lambda _event: self.show_composer_menu())
        input_shell.tag_bind("expand-action", "<Button-1>", lambda _event: self.toggle_input_expanded())
        input_shell.tag_bind("prompt-action", "<Button-1>", lambda _event: self.handle_prompt_action())
        input_shell.tag_bind("send-action", "<Button-1>", lambda _event: self._send_input())
        self.send_btn = input_shell
        self.send_btn._text_item = "send-icon"
        def _resize_input(event):
            input_shell.delete("rounded-bg")
            action_y = event.height - 19
            self._draw_round_rect(input_shell, 1, 1, event.width - 1, event.height - 1, 15, fill=card, outline="#dbe2ea", tags="rounded-bg")
            input_shell.tag_lower("rounded-bg")
            input_shell.itemconfigure(input_window, width=max(100, event.width - 48), height=max(18, event.height - 37))
            input_shell.coords(add_icon_item, 22, action_y)
            input_shell.coords(expand_icon_item, event.width - 16, 14)
            input_shell.coords(prompt_icon_item, event.width - 50, action_y)
            input_shell.coords(send_icon_item, event.width - 19, action_y)
            input_shell.tag_raise(add_icon_item)
            input_shell.tag_raise(expand_icon_item)
            input_shell.tag_raise(prompt_icon_item)
            input_shell.tag_raise(send_icon_item)
        input_shell.bind("<Configure>", _resize_input)

        body = tk.Frame(shell, bg=bg)
        body.pack(fill="both", expand=True)
        task_section = tk.Frame(body, bg=bg)
        task_section.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        self.summary_frame = tk.Frame(task_section, bg=bg)
        self.summary_frame.pack_forget()
        self.context_tools_frame = tk.Frame(task_section, bg=bg)
        self.context_tools_frame.pack(fill="x", pady=(0, 3))
        tabs = tk.Frame(task_section, bg=bg)
        tabs.pack(fill="x", pady=(0, 3))
        self.tab_buttons = {}
        self.tab_lines = {}
        for key, label in (("create", "创建任务"), ("manage", "任务管理"), ("tools", "工具")):
            cell = tk.Frame(tabs, bg=bg)
            cell.pack(side="left", fill="x", expand=True)
            button = tk.Button(
                cell,
                text=label,
                command=lambda value=key: self.select_tab(value),
                relief="flat",
                bd=0,
                bg=bg,
                fg="#657084",
                activebackground=bg,
                activeforeground="#0867f2",
                font=("Microsoft YaHei UI", 8),
                padx=6,
                pady=1,
                cursor="hand2",
                highlightthickness=0,
            )
            button.pack(fill="x")
            line = tk.Frame(cell, bg="#dbe2ea", height=2)
            line.pack(fill="x", padx=12)
            self.tab_buttons[key] = button
            self.tab_lines[key] = line
        self.task_canvas = tk.Canvas(task_section, bg=bg, highlightthickness=0, bd=0)
        self.task_canvas.pack(fill="both", expand=True)
        self.task_frame = tk.Frame(self.task_canvas, bg=bg)
        self.task_canvas_window = self.task_canvas.create_window(0, 0, anchor="nw", window=self.task_frame)
        self.task_frame.bind(
            "<Configure>",
            lambda _event: self.task_canvas.configure(scrollregion=self.task_canvas.bbox("all")),
        )
        self.task_canvas.bind(
            "<Configure>",
            lambda event: self.task_canvas.itemconfigure(self.task_canvas_window, width=event.width),
        )
        self.root.bind("<MouseWheel>", self._on_task_scroll)
        self.status_label = tk.Label(task_section, text="正在连接 AideLink 服务...", fg=muted, bg=bg, anchor="w")
        self.status_label.pack(fill="x", pady=(4, 0))

    def _enable_rounded_window(self):
        if os.name != "nt":
            return
        try:
            preference = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                self.root.winfo_id(),
                33,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except (AttributeError, OSError):
            pass

    def _flat_button(self, parent, text, command):
        return self.tk.Button(parent, text=text, command=command, relief="flat", bd=0, bg="#ffffff", fg="#283246", activebackground="#f1f5f9", activeforeground="#0867f2", font=("Microsoft YaHei UI", 9), padx=10, pady=7)

    def _icon_button(self, parent, icon_name, command, size=18, color="#263246"):
        return self.tk.Button(
            parent,
            image=self.icons.get(icon_name, size, color),
            command=command,
            relief="flat",
            bd=0,
            bg="#ffffff",
            activebackground="#f1f5f9",
            cursor="hand2",
            padx=7,
            pady=6,
        )

    @staticmethod
    def _draw_round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _rounded_button(self, parent, text, command, width, height, fill, outline, fg, bold=False, font_size=10, radius=16, icon_name=None, icon_size=17, dot_color=None):
        canvas = self.tk.Canvas(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, cursor="hand2")
        canvas._shape_item = self._draw_round_rect(canvas, 1, 1, width - 1, height - 1, radius, fill=fill, outline=outline, width=1)
        canvas._command = command
        font = ("Microsoft YaHei UI", font_size, "bold" if bold else "normal")
        if icon_name:
            icon = self.icons.get(icon_name, icon_size, fg)
            canvas._icon_image = icon
            if text:
                canvas.create_image(width / 2 - 8, height / 2, image=icon)
                canvas._text_item = canvas.create_text(width / 2 + 10, height / 2, text=text, fill=fg, font=font)
            else:
                canvas._text_item = canvas.create_image(width / 2, height / 2, image=icon)
        elif dot_color:
            canvas.create_oval(12, height / 2 - 4, 20, height / 2 + 4, fill=dot_color, outline=dot_color)
            canvas._text_item = canvas.create_text(width / 2 + 5, height / 2, text=text, fill=fg, font=font)
        else:
            canvas._text_item = canvas.create_text(width / 2, height / 2, text=text, fill=fg, font=font)
        canvas.bind("<Button-1>", lambda _event: command())
        return canvas

    def _ide_button(self, parent, ide, selected):
        width, height = 30, 30
        canvas = self.tk.Canvas(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, cursor="hand2")
        badge = self.icons.ide_badge(ide["key"], ide.get("path"), selected=selected, size=30)
        canvas._ide_badge = badge
        canvas.create_image(15, 15, image=badge)
        canvas.bind("<Button-1>", lambda _event, key=ide["key"]: self.select_ide(key))
        return canvas

    def _draw_group_header(self, canvas, width, fill, outline, fg, name, count, icon, collapsed=False, show_chevron=True):
        canvas.delete("all")
        icon_image = self.icons.get(icon, 12, fg)
        chevron_image = (
            self.icons.get("chevron_down" if collapsed else "chevron_up", 12, "#526078")
            if show_chevron else None
        )
        canvas._header_images = tuple(image for image in (icon_image, chevron_image) if image)
        canvas.create_image(9, 11, image=icon_image)
        canvas.create_text(21, 11, text=f"{name}  {count}", fill=fg, anchor="w", font=("Microsoft YaHei UI", 8, "bold"))
        if chevron_image:
            canvas.create_image(width - 10, 11, image=chevron_image)

    def _draw_task_card(self, canvas, width, task, type_labels, latest_running=False):
        canvas.delete("all")
        height = int(canvas.cget("height"))
        base_height = self._task_base_height(task)
        test_result = _task_test_result(task)
        if _task_group_name(task) == "待派发":
            card_outline = "#9b7be3"
        elif _task_group_name(task) == "待测试" and test_result == "queued":
            card_outline = "#0867f2"
        elif _task_group_name(task) == "待测试" and test_result in {"dispatched", "passed"}:
            card_outline = "#2e9d55"
        elif _task_group_name(task) == "待测试" and test_result == "failed":
            card_outline = "#d83b3b"
        elif _task_group_name(task) == "待测试":
            card_outline = "#f08a00"
        elif latest_running:
            card_outline = "#35b86b"
        else:
            card_outline = "#e1e6ed"
        self._draw_round_rect(canvas, 1, 1, width - 1, height - 1, 12, fill="#ffffff", outline=card_outline, tags="card-hit")
        body = _clean_task_text(task.get("text") or task.get("title")) or "无内容"
        show_test_checkbox = (
            _task_group_name(task) == "待测试"
            and self.test_selection_mode
        )
        body_x = 32 if show_test_checkbox else 12
        canvas.create_text(body_x, 9, text=body, fill="#20293a", anchor="nw", width=max(130, width - body_x - 40), font=("Microsoft YaHei UI", 9), tags="card-hit")
        if show_test_checkbox:
            selected = task.get("task_id") in self.selected_test_task_ids
            tag = f"select-test-{task.get('task_id')}"
            self._draw_round_rect(canvas, 10, 9, 25, 24, 4, fill="#0867f2" if selected else "#ffffff", outline="#0867f2", tags=tag)
            if selected:
                canvas.create_text(17.5, 16.5, text="✓", fill="#ffffff", font=("Microsoft YaHei UI", 9, "bold"), tags=tag)
            canvas.tag_bind(tag, "<Button-1>", lambda _event, item=task: (self.toggle_test_selection(item.get("task_id")), "break")[-1])

        metadata_y = base_height - 16
        version = str(task.get("version") or "").strip()
        version_text = f"v{version}" if version and not version.lower().startswith("v") else (version or "v--")
        self._draw_round_rect(canvas, 12, metadata_y - 9, 76, metadata_y + 9, 6, fill="#f3f5f8", outline="#e3e7ed", tags="card-hit")
        canvas.create_text(44, metadata_y, text=version_text[:12], fill="#657084", font=("Microsoft YaHei UI", 8), tags="card-hit")
        display_status = (
            "测试通过" if test_result == "passed"
            else "测试排队中" if test_result == "queued"
            else "测试已派发" if test_result == "dispatched"
            else "测试未通过" if test_result == "failed"
            else task["status"]
        )
        subtitle = f"{task['target_ide']}  ·  {display_status}"
        progress = max(0, min(100, task.get("progress") or 0))
        if task["status"] == "执行中" and progress:
            subtitle += f"  ·  {progress}%"
        canvas.create_text(84, metadata_y, text=subtitle, fill="#657084", anchor="w", font=("Microsoft YaHei UI", 8), tags="card-hit")

        # 待测试卡片右侧图标是“原任务重新派发”；“派发测试”只放在展开操作里。
        dispatch_action = "dispatch"
        dispatch_label = "派发"
        actions = (
            (("复制", "copy", 14), ("已完成", "confirm_done", 36), (dispatch_label, dispatch_action, 58))
            if _task_group_name(task) == "待测试"
            else (("复制", "copy", 14), (dispatch_label, dispatch_action, 36))
        )
        action_images = []
        for action, action_name, center_y in actions:
            tag = f"{action}-{task.get('task_id')}"
            if action_name == "confirm_done":
                self._draw_round_rect(
                    canvas, width - 43, center_y - 9, width - 5, center_y + 9, 6,
                    fill="#effaf3", outline="#8fd3a8", tags=tag,
                )
                canvas.create_text(
                    width - 24, center_y, text="完成", fill="#24864b",
                    font=("Microsoft YaHei UI", 7, "bold"), tags=tag,
                )
            else:
                # 图标保持 12px，但给它一个稳定的 32x24 点击热区。
                # 之前只有图标本身响应点击，点到右侧空白时会落到 card-hit，
                # 表现为“没有进入派发流程”。
                self._draw_round_rect(
                    canvas, width - 34, center_y - 12, width - 2, center_y + 12, 7,
                    fill="#ffffff", outline="", tags=tag,
                )
                icon_name = "copy" if action_name == "copy" else "dispatch"
                action_image = self.icons.get(icon_name, 12, "#526078")
                action_images.append(action_image)
                canvas.create_image(width - 16, center_y, image=action_image, tags=tag)
            callback = (
                (lambda _event, item=task: (self.copy_task(item), "break")[-1])
                if action_name == "copy"
                else (
                    lambda _event, value=action_name, item=task:
                    (self.execute_task_action(value, item), "break")[-1]
                )
            )
            canvas.tag_bind(tag, "<Button-1>", callback)
        images = [*action_images]
        if self.expanded_task_id == task.get("task_id"):
            canvas.create_line(10, base_height, width - 10, base_height, fill="#edf0f4")
            for index, (action, label) in enumerate(self._expanded_actions(task)):
                row, column = divmod(index, 4)
                x1 = 10 + column * 78
                y1 = base_height + 6 + row * 27
                x2, y2 = x1 + 70, y1 + 21
                tag = f"expanded-{action}-{task.get('task_id')}"
                self._draw_round_rect(canvas, x1, y1, x2, y2, 7, fill="#ffffff", outline="#dbe2ea", tags=tag)
                canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill="#526078", font=("Microsoft YaHei UI", 7), tags=tag)
                if action == "view":
                    callback = lambda _event, item=task: (self.view_task(item), "break")[-1]
                elif action == "smart_prompt":
                    callback = lambda _event, item=task: (self.compose_task_smart_prompt(item), "break")[-1]
                else:
                    callback = lambda _event, value=action, item=task: (self.execute_task_action(value, item), "break")[-1]
                canvas.tag_bind(tag, "<Button-1>", callback)
        canvas._task_images = tuple(images)
        canvas.tag_bind("card-hit", "<Button-1>", lambda _event, item=task: self.toggle_task_more(item.get("task_id")))

    @staticmethod
    def _task_base_height(task):
        body = _clean_task_text(task.get("text") or task.get("title")) or ""
        lines = 0
        for paragraph in body.splitlines() or [""]:
            lines += max(1, (len(paragraph) + 20) // 21)
        return max(68, 37 + lines * 16)

    def _task_card_height(self, task):
        height = self._task_base_height(task)
        if self.expanded_task_id == task.get("task_id"):
            actions = self._expanded_actions(task)
            height += 8 + ((len(actions) + 3) // 4) * 27
        return height

    @staticmethod
    def _expanded_actions(task):
        actions = [
            ("edit", "编辑"),
            ("smart_prompt", "智能提示词"),
        ]
        if _task_group_name(task) == "进行中":
            actions.append(("pending_test", "待测试"))
        if _task_group_name(task) == "待测试":
            test_result = _task_test_result(task)
            if test_result != "passed":
                actions.append(("test_feedback", "测试反馈"))
            if test_result == "failed":
                actions.append(("send_test_feedback", "反馈开发 IDE"))
            if test_result in {"dispatched", "passed"}:
                actions.append(("confirm_done", "确认完成"))
            else:
                actions.append(("confirm_done", "已完成"))
            actions.append((
                "dispatch_test",
                "重新测试" if test_result else "派发测试",
            ))
        else:
            actions.append(("complete", "已完成"))
        actions.append(("delete", "删除"))
        return tuple(actions)

    def _render_task_tab(self, tasks, summary_styles, group_names=None):
        tk = self.tk
        type_labels = {
            "android": ("Android", "#effaf3", "#24864b", "smartphone"),
            "web": ("Web", "#eff6ff", "#0867f2", "globe"),
            "general": ("通用", "#f4f1ff", "#7657d9", "bot"),
        }
        all_groups = (
            ("待派发", [task for task in tasks if _task_group_name(task) == "待派发"]),
            ("进行中", [task for task in tasks if _task_group_name(task) == "进行中"]),
            ("待测试", [task for task in tasks if _task_group_name(task) == "待测试"]),
            ("已完成", [task for task in tasks if _task_group_name(task) == "已完成"]),
        )
        visible_names = set(group_names or (name for name, _items in all_groups))
        groups = tuple((name, items) for name, items in all_groups if name in visible_names)
        running_tasks = next((items for name, items in groups if name == "进行中"), [])
        latest_running_id = _latest_task_id(running_tasks)
        for group_name, group_tasks in groups:
            if not group_tasks:
                continue
            collapsed = group_name in self.collapsed_groups
            group_bg, group_fg, group_border = summary_styles[group_name]
            icon = {"待派发": "alert", "待测试": "clock", "进行中": "loader", "已完成": "copy"}[group_name]
            header_count = (
                int(self.current_model.get("summary", {}).get("已完成") or len(group_tasks))
                if group_name == "已完成"
                else len(group_tasks)
            )
            header_row = tk.Frame(self.task_frame, bg="#ffffff", height=22)
            header_row.pack(fill="x", pady=(0, 2))
            header_row.pack_propagate(False)
            header = tk.Canvas(header_row, height=22, bg="#ffffff", highlightthickness=0)
            header.bind("<Configure>", lambda event, canvas=header, bg=group_bg, border=group_border, fg=group_fg, name=group_name, count=header_count, symbol=icon, is_collapsed=collapsed: self._draw_group_header(canvas, event.width, bg, border, fg, name, count, symbol, is_collapsed, name != "待测试"))
            header.bind("<Button-1>", lambda _event, name=group_name: self.toggle_group(name))
            if group_name == "待测试":
                selected_count = len(self.selected_test_task_ids)
                chevron = tk.Canvas(
                    header_row, width=20, height=22, bg="#ffffff",
                    highlightthickness=0, cursor="hand2",
                )
                chevron_image = self.icons.get(
                    "chevron_down" if collapsed else "chevron_up", 12, "#526078",
                )
                chevron._header_image = chevron_image
                chevron.create_image(10, 11, image=chevron_image)
                chevron.bind("<Button-1>", lambda _event: self.toggle_group("待测试"))
                chevron.pack(side="right")
                if self.test_selection_mode and selected_count >= 2:
                    queue_button = tk.Button(
                        header_row,
                        text=f"排队测试（{selected_count}）",
                        command=self.dispatch_selected_tests,
                        relief="flat",
                        bg="#0867f2",
                        fg="#ffffff",
                        cursor="hand2",
                        font=("Microsoft YaHei UI", 7, "bold"),
                        width=11,
                        padx=2,
                        pady=0,
                    )
                    queue_button.pack(side="right", padx=(3, 0))
                tk.Button(
                    header_row,
                    text="取消" if self.test_selection_mode else "多选",
                    command=self.toggle_test_selection_mode,
                    relief="flat",
                    bg="#f3f5f8",
                    fg="#526078",
                    cursor="hand2",
                    font=("Microsoft YaHei UI", 7),
                    width=4,
                    padx=2,
                    pady=0,
                ).pack(side="right")
            # 右侧操作先占据其请求宽度，标题画布最后填充剩余空间。
            # 如果先 pack(expand=True) 标题，Tk 会把后加入的中文按钮压到约一个字宽。
            header.pack(side="left", fill="both", expand=True)
            if collapsed:
                continue
            visible_group_tasks = (
                group_tasks[:self.completed_display_limit]
                if group_name == "已完成"
                else group_tasks
            )
            for task in visible_group_tasks:
                task_card = tk.Canvas(self.task_frame, height=self._task_card_height(task), bg="#ffffff", highlightthickness=0, cursor="hand2")
                task_card.pack(fill="x", pady=(0, 4))
                is_latest_running = (
                    group_name == "进行中"
                    and task.get("task_id") == latest_running_id
                )
                task_card.bind(
                    "<Configure>",
                    lambda event, canvas=task_card, item=task, labels=type_labels, highlighted=is_latest_running:
                        self._draw_task_card(canvas, event.width, item, labels, highlighted),
                )
            if group_name == "已完成" and len(group_tasks) > len(visible_group_tasks):
                remaining = len(group_tasks) - len(visible_group_tasks)
                more = tk.Label(
                    self.task_frame,
                    text=f"显示更多（还有 {remaining} 条）",
                    bg="#ffffff",
                    fg="#0867f2",
                    font=("Microsoft YaHei UI", 8),
                    cursor="hand2",
                    pady=4,
                )
                more.pack(fill="x", pady=(0, 4))
                more.bind("<Button-1>", lambda _event: self.show_more_completed())

    def _render_create_tab(self, tasks, summary_styles):
        pending = [task for task in tasks if _task_group_name(task) == "待派发"]
        if pending:
            self._render_task_tab(pending, summary_styles, group_names=("待派发",))
        else:
            self.tk.Label(
                self.task_frame,
                text="暂无待派发任务",
                bg="#ffffff",
                fg="#8a94a6",
                anchor="w",
                font=("Microsoft YaHei UI", 8),
            ).pack(fill="x", padx=3, pady=(3, 8))
        self._render_prompt_builder()

    def _render_prompt_builder(self):
        tk = self.tk
        panel = tk.Frame(
            self.task_frame,
            bg="#f8faff",
            highlightbackground="#d8e3f5",
            highlightthickness=1,
        )
        panel.pack(fill="x", pady=(2, 6), ipady=7)

        heading = tk.Frame(panel, bg="#f8faff")
        heading.pack(fill="x", padx=9, pady=(1, 6))
        tk.Label(
            heading,
            text="修改目标",
            bg="#f8faff",
            fg="#263246",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left")
        tk.Label(
            heading,
            text="点击目标插入输入框，右键可移除",
            bg="#f8faff",
            fg="#7a8496",
            font=("Microsoft YaHei UI", 7),
        ).pack(side="right")

        tk.Label(
            panel,
            text="任务类型",
            bg="#f8faff",
            fg="#657084",
            anchor="w",
            font=("Microsoft YaHei UI", 7),
        ).pack(fill="x", padx=9)
        type_row = tk.Frame(panel, bg="#f8faff")
        type_row.pack(fill="x", padx=8, pady=(2, 6))
        selected_type = getattr(self, "prompt_task_type", "unspecified")
        for index, (key, label) in enumerate(PROMPT_TASK_TYPES):
            active = key == selected_type
            type_row.columnconfigure(index, weight=1)
            tk.Button(
                type_row,
                text=label,
                command=lambda value=key: self.select_prompt_task_type(value),
                relief="flat",
                bd=0,
                bg="#0867f2" if active else "#edf2fa",
                fg="#ffffff" if active else "#526078",
                activebackground="#0757cd" if active else "#e3eaf5",
                activeforeground="#ffffff" if active else "#263246",
                font=("Microsoft YaHei UI", 7, "bold" if active else "normal"),
                padx=2,
                pady=3,
                cursor="hand2",
            ).grid(row=0, column=index, sticky="ew", padx=2)

        target_row = tk.Frame(panel, bg="#f8faff")
        target_row.pack(fill="x", padx=9, pady=(0, 2))
        pool = self._current_component_pool()
        for item in pool[:6]:
            phrase = self._component_phrase(item)
            short_label = str(item.get("name") or phrase).strip()
            if len(short_label) > 12:
                short_label = short_label[:11] + "…"
            button = tk.Button(
                target_row,
                text=short_label,
                command=lambda value=item: self.insert_component_target(value),
                relief="flat", bd=0, bg="#edf2fa", fg="#40516b",
                activebackground="#dde8f8", font=("Microsoft YaHei UI", 7),
                padx=6, pady=3, cursor="hand2",
            )
            button.pack(side="left", padx=(0, 4), pady=2)
            button.bind("<Button-3>", lambda _event, value=item: self.remove_component_target(value))
        if len(pool) > 6:
            tk.Button(
                target_row, text=f"更多 {len(pool) - 6}",
                command=self.show_component_pool_menu,
                relief="flat", bd=0, bg="#f3f5f8", fg="#657084",
                font=("Microsoft YaHei UI", 7), padx=5, pady=3,
            ).pack(side="left", padx=(0, 4))
        tk.Button(
            target_row,
            text="＋ 添加目标",
            command=self.open_prompt_component_locator,
            relief="flat",
            bg="#edf2fa",
            fg="#526078",
            activebackground="#e3eaf5",
            font=("Microsoft YaHei UI", 7),
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side="left")

        candidates = getattr(self, "prompt_candidates", []) or []
        if candidates:
            tk.Frame(panel, bg="#dbe3ef", height=1).pack(fill="x", padx=9, pady=(7, 4))
            for index, candidate in enumerate(candidates[:3]):
                title = str(candidate.get("title") or f"候选 {index + 1}").strip()
                understanding = str(candidate.get("understanding") or "").strip()
                label = title if not understanding else f"{title} · {understanding}"
                button = tk.Button(
                    panel,
                    text=label,
                    command=lambda value=index: self.select_prompt_candidate(value),
                    relief="flat",
                    bd=0,
                    bg="#ffffff",
                    fg="#3f4d63",
                    activebackground="#edf4ff",
                    activeforeground="#0867f2",
                    anchor="w",
                    justify="left",
                    wraplength=max(220, self.window_width - 48),
                    font=("Microsoft YaHei UI", 7),
                    padx=8,
                    pady=4,
                    cursor="hand2",
                )
                button.pack(fill="x", padx=9, pady=(0, 3))

    def _render_tools_tab(self):
        tools = (
            ("快捷回复", "more", self.show_quick_reply_menu),
            ("组件定位", "globe", self.open_prompt_component_locator),
            ("设置", "settings", self.open_settings),
        )
        for label, icon, command in tools:
            button = self._rounded_button(
                self.task_frame, label, command,
                width=88, height=34, fill="#ffffff", outline="#dbe2ea",
                fg="#3f4d63", font_size=8, icon_name=icon, icon_size=14, radius=10,
            )
            button.pack(side="left", padx=(0, 5), pady=3)

    def _clear_rows(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _render(self, model):
        tk = self.tk
        project_key = model.get("project_path") or model.get("project_name") or ""
        if project_key != self.surface_project_key:
            self.surface_project_key = project_key
            self.selected_surface = None
        platforms = _project_platforms(model.get("capabilities"))
        if len(platforms) < 2 or self.selected_surface not in platforms:
            self.selected_surface = None
        self.current_model = model
        self.selected_ide_key = choose_selected_ide(
            self.selected_ide_key,
            model["ides"],
            model.get("selected_target_key"),
        )
        self.root.title(model["title"])
        visible_tasks = [task for task in model["tasks"] if task.get("content_kind") != "inspiration"]
        pending_ids = {
            task.get("task_id") for task in visible_tasks
            if _task_group_name(task) == "待测试" and task.get("task_id")
        }
        self.selected_test_task_ids.intersection_update(pending_ids)
        if self.active_tab == "create":
            pending = [
                task for task in visible_tasks
                if _task_group_name(task) == "待派发"
            ]
            content_height = (
                sum(self._task_card_height(task) + 4 for task in pending)
                + (24 if pending else 28)
                + 185
                + min(3, len(getattr(self, "prompt_candidates", []) or [])) * 38
            )
        elif self.active_tab == "manage":
            grouped = (
                ("进行中", [task for task in visible_tasks if _task_group_name(task) == "进行中"]),
                ("待测试", [task for task in visible_tasks if _task_group_name(task) == "待测试"]),
                ("已完成", [task for task in visible_tasks if _task_group_name(task) == "已完成"]),
            )
            group_count = sum(bool(items) for _name, items in grouped)
            expanded_tasks = []
            has_more_completed = False
            for name, items in grouped:
                if name in self.collapsed_groups:
                    continue
                if name == "已完成":
                    expanded_tasks.extend(items[:self.completed_display_limit])
                    has_more_completed = len(items) > self.completed_display_limit
                else:
                    expanded_tasks.extend(items)
            content_height = (
                sum(self._task_card_height(task) + 4 for task in expanded_tasks)
                + group_count * 24
                + (24 if has_more_completed else 0)
            )
        else:
            content_height = 42
        compact_height = max(self.min_window_height, min(self.max_window_height, 260 + content_height))
        self.root.geometry(f"{self.window_width}x{compact_height}")
        self.root.after_idle(lambda height=compact_height: self._ensure_window_visible(height))
        self.title_label.config(text=model["project_name"])
        self._render_capability_icons(model["capabilities"])
        self._render_context_tools(model["capabilities"])
        self._set_status("")

        self._clear_rows(self.ide_frame)
        running = [ide for ide in model["ides"] if ide["running"]]
        stopped = [ide for ide in model["ides"] if not ide["running"]]
        if running:
            for ide in running:
                selected = ide["key"] == self.selected_ide_key
                button = self._ide_button(self.ide_frame, ide, selected)
                button.pack(side="left", padx=(0, 5))
        else:
            tk.Label(self.ide_frame, text="暂无运行中的 IDE", bg="#ffffff", fg="#777f8f", anchor="w").pack(side="left", fill="x", expand=True, pady=7)
        if stopped:
            self._rounded_button(
                self.ide_frame, "", lambda: self.show_launch_menu(stopped),
                width=28, height=28, fill="#ffffff", outline="#ffffff", fg="#0867f2",
                icon_name="plus", icon_size=14,
            ).pack(side="right")

        self._clear_rows(self.summary_frame)
        summary_styles = {
            "待派发": ("#f7f2ff", "#7657d9", "#d9cbf7"),
            "待测试": ("#fff9ef", "#f08a00", "#f5d8ae"),
            "进行中": ("#f3f8ff", "#0867f2", "#c9dcfb"),
            "已完成": ("#f1faf4", "#24864b", "#c5e8d0"),
        }
        for key, button in self.tab_buttons.items():
            active = key == self.active_tab
            button.config(
                fg="#0867f2" if active else "#657084",
                bg="#ffffff",
                font=("Microsoft YaHei UI", 8, "bold" if active else "normal"),
            )
            self.tab_lines[key].config(bg="#0867f2" if active else "#dbe2ea")
        self._clear_rows(self.task_frame)
        tasks = [task for task in model["tasks"] if task.get("content_kind") != "inspiration"]
        if self.active_tab == "create":
            self._render_create_tab(tasks, summary_styles)
        elif self.active_tab == "tools":
            self._render_tools_tab()
        elif any(_task_group_name(task) != "待派发" for task in tasks):
            self._render_task_tab(
                tasks,
                summary_styles,
                group_names=("进行中", "待测试", "已完成"),
            )
        else:
            tk.Label(
                self.task_frame,
                text="暂无进行中、待测试或已完成任务",
                bg="#ffffff",
                fg="#777f8f",
                anchor="w",
            ).pack(fill="x", pady=10)

        selected_ide = next((ide for ide in model["ides"] if ide["key"] == self.selected_ide_key), None)
        if self.active_tab == "create":
            self.send_btn.itemconfigure(
                self.send_btn._text_item,
                image=self.icons.get("send", 20, "#0867f2"),
            )
            self.send_btn.tag_bind(
                "send-action",
                "<Button-1>",
                lambda _event: self.create_task(),
            )
        elif selected_ide:
            self.send_btn.itemconfigure(self.send_btn._text_item, image=self.icons.get("send", 20, "#0867f2"))
            self.send_btn.tag_bind("send-action", "<Button-1>", lambda _event: self._send_input())
        else:
            self.send_btn.itemconfigure(self.send_btn._text_item, image=self.icons.get("send", 19, "#8a94a6"))
            self.send_btn.tag_unbind("send-action", "<Button-1>")

    def _render_capability_icons(self, capabilities):
        self._clear_rows(self.capability_frame)
        platforms = _project_platforms(capabilities)
        selectable = len(platforms) > 1
        rendered = False
        for capability, icon_name, color, label in PLATFORM_SPECS:
            if capability not in capabilities:
                continue
            selected = self.selected_surface == capability
            icon_color = color if (selected or not selectable) else "#a8b0bd"
            widget = self.tk.Label(
                self.capability_frame,
                image=self.icons.get(icon_name, 17, icon_color),
                bg="#ffffff",
                padx=2,
                cursor="hand2" if selectable else "",
            )
            widget.pack(side="left")
            if selectable:
                widget.bind(
                    "<Button-1>",
                    lambda _event, value=capability: self.select_surface(value),
                )
            rendered = True
        if not rendered:
            self.tk.Label(
                self.capability_frame,
                image=self.icons.get("bot", 17, "#657084"),
                bg="#ffffff",
                padx=2,
            ).pack(side="left")

    def select_surface(self, surface):
        platforms = _project_platforms(self.current_model.get("capabilities"))
        if len(platforms) < 2 or surface not in platforms:
            return
        self.selected_surface = None if self.selected_surface == surface else surface
        self._render(self.current_model)

    def _active_tool_surface(self, capabilities):
        platforms = _project_platforms(capabilities)
        if len(platforms) == 1:
            return platforms[0]
        selected_surface = getattr(self, "selected_surface", None)
        return selected_surface if selected_surface in platforms else None

    def _ensure_context_tools_visible(self):
        """安全地让 context_tools_frame 可见，避免索引越界崩溃。"""
        frame = self.context_tools_frame
        if frame.winfo_manager():
            return
        # 尝试插在 tabs 之前；找不到就普通 pack
        try:
            siblings = frame.master.winfo_children()
            # 找到第一个在 frame 之后创建的同级组件（tabs/任务列表等）作为锚点
            anchor = None
            for widget in siblings:
                if widget is frame:
                    continue
                if widget.winfo_manager():
                    anchor = widget
                    break
            if anchor is not None and anchor is not frame:
                frame.pack(fill="x", pady=(0, 3), before=anchor)
            else:
                frame.pack(fill="x", pady=(0, 3))
        except Exception:
            frame.pack(fill="x", pady=(0, 3))

    def _render_context_tools(self, capabilities):
        self._clear_rows(self.context_tools_frame)
        surface = self._active_tool_surface(capabilities)
        if surface == "android":
            # Android 平台直接渲染设备列表（每台设备自带 [📷][⚡安装] 等入口），
            # 不再用顶部统一的「连接/复制地址/截图反馈」按钮行。
            self._render_android_devices()
            return
        tools = {
            "web": (
                ("刷新页面", "loader", self.refresh_web_page),
                ("组件定位", "globe", self.open_web_component_locator),
            ),
            "windows": (
                ("截图反馈", "windows", self.windows_screenshot_feedback),
                ("窗口定位", "expand", self.locate_windows_target),
            ),
        }.get(surface, ())
        if not tools:
            self.context_tools_frame.pack_forget()
            return
        self._ensure_context_tools_visible()
        for label, icon, command in tools:
            button = self._rounded_button(
                self.context_tools_frame,
                label,
                command,
                width=82,
                height=27,
                fill="#ffffff",
                outline="#e1e6ed",
                fg="#526078",
                font_size=7,
                icon_name=icon,
                icon_size=12,
                radius=9,
            )
            button.pack(side="left", padx=(0, 4))

    def _render_android_devices(self):
        """渲染 Android 设备列表：每台设备一行，含 [📷截图][⚡安装] 入口。

        状态判定（两个数据源都断才算真离线）：
        - is_aidelink_online = is_online || is_active（120s 内有 SSE 心跳）
        - is_adb_online = is_adb_connected（adb devices 能看到）
        - 真离线 = not is_aidelink_online AND not is_adb_online

        点设备名：在线时复制 ip:port，真离线无操作。
        点状态标签：恢复另一个连接（🟡AideLink在线→恢复ADB；🟡ADB在线→恢复AideLink）。

        [⚡安装]：AideLink 在线走 connect+install；仅 ADB 在线走直接 install；真离线置灰
        [📷截图]：仅 AideLink 在线时可点（需要 SSE 推送）；仅 ADB 在线时置灰
        """
        frame = self.context_tools_frame
        self._ensure_context_tools_visible()

        # 占位标签，等异步加载后替换
        loading = self.tk.Label(frame, text="正在读取设备…", bg="#ffffff", fg="#657084",
                                font=("Microsoft YaHei", 8))
        loading.pack(side="left", padx=(2, 0))

        def render(result):
            for child in frame.winfo_children():
                child.destroy()
            devices = result.get("devices") or []
            if not devices:
                self.tk.Label(
                    frame, text="暂无已连接设备，请打开 AideLink App",
                    bg="#ffffff", fg="#b42318", font=("Microsoft YaHei", 8),
                ).pack(side="left", padx=(2, 0))
                return

            for device in devices:
                row = self.tk.Frame(frame, bg="#ffffff")
                row.pack(fill="x", pady=(0, 2))

                alias = device.get("alias")
                ip = device.get("online_ip") or device.get("ip")
                port = device.get("adb_port") or 5555
                # 两个独立的在线状态
                is_aidelink_online = bool(device.get("is_online") or device.get("is_active"))
                is_adb_online = bool(device.get("is_adb_connected"))
                is_truly_offline = not is_aidelink_online and not is_adb_online

                # 设备名（在线时点击复制地址，真离线无操作）
                if alias:
                    name_text = f"{alias} ({ip})" if ip else alias
                else:
                    name_text = ip or "未知设备"
                name_color = "#239957" if not is_truly_offline else "#b42318"
                name_label = self.tk.Label(
                    row, text=f"📱 {name_text}",
                    bg="#ffffff", fg=name_color,
                    font=("Microsoft YaHei", 8, "bold"),
                    cursor="hand2" if not is_truly_offline else "arrow",
                )
                name_label.pack(side="left", padx=(2, 6))
                if not is_truly_offline:
                    name_label.bind(
                        "<Button-1>",
                        lambda _e, d=device: self._copy_device_address(d),
                    )

                # 状态标签（四态显示 + 点击恢复另一个连接）
                if is_aidelink_online and is_adb_online:
                    status_text = "🟢全在线"
                    status_color = "#239957"
                    status_cursor = "arrow"
                elif is_aidelink_online and not is_adb_online:
                    status_text = "🟡AideLink在线"
                    status_color = "#b8860b"
                    status_cursor = "hand2"
                elif is_adb_online and not is_aidelink_online:
                    status_text = "🟡ADB在线"
                    status_color = "#b8860b"
                    status_cursor = "hand2"
                else:
                    status_text = "⚪离线"
                    status_color = "#657084"
                    status_cursor = "arrow"
                status_label = self.tk.Label(
                    row, text=status_text, bg="#ffffff", fg=status_color,
                    font=("Microsoft YaHei", 7),
                    cursor=status_cursor,
                )
                status_label.pack(side="left", padx=(0, 6))
                # 点状态标签：恢复另一个连接
                if is_aidelink_online and not is_adb_online:
                    # AideLink 在线但 ADB 不在线 → 恢复 ADB（enable_wireless + adb connect）
                    status_label.bind(
                        "<Button-1>",
                        lambda _e, d=device: self._connect_device(d),
                    )
                elif is_adb_online and not is_aidelink_online:
                    # ADB 在线但 AideLink 不在线 → 恢复 AideLink（start-foreground-service）
                    status_label.bind(
                        "<Button-1>",
                        lambda _e, d=device: self._launch_app_service(d),
                    )

                # 未配 alias 设备额外显示 [🏷别名] 按钮
                if not alias and ip:
                    self._rounded_button(
                        row, "🏷别名",
                        lambda d=device: self._set_alias_for_device(d),
                        width=58, height=22,
                        fill="#ffffff", outline="#e1e6ed", fg="#526078",
                        font_size=7, icon_name="tag", icon_size=10, radius=8,
                    ).pack(side="left", padx=(0, 4))

                # [📷截图] 按钮：仅 AideLink 在线时可点（需要 SSE 推送命令到 App）
                # 仅 ADB 在线但 AideLink 不在线时置灰——无法推送命令
                screenshot_enabled = is_aidelink_online
                screenshot_cmd = (
                    (lambda d=device: self.android_screenshot_feedback(d))
                    if screenshot_enabled else
                    (lambda: self._set_status(
                        "AideLink 不在线，无法推送截图命令；点状态标签可拉起服务"
                        if is_adb_online else
                        "AideLink 不在线，无法推送截图命令；请先在手机上打开 AideLink App",
                        "#b42318", 2200,
                    ))
                )
                self._rounded_button(
                    row, "📷",
                    screenshot_cmd,
                    width=32, height=22,
                    fill="#ffffff" if screenshot_enabled else "#f0f3f8",
                    outline="#e1e6ed" if screenshot_enabled else "#e1e6ed",
                    fg="#526078" if screenshot_enabled else "#b4c0d0",
                    font_size=8, radius=8,
                ).pack(side="left", padx=(0, 4))

                # [⚡安装] 按钮：AideLink 在线走 connect+install；仅 ADB 在线走直接 install；真离线置灰
                install_enabled = not is_truly_offline
                install_cmd = (
                    (lambda d=device: self._install_apk_to_device(d, force_adb_only=is_adb_online and not is_aidelink_online))
                    if install_enabled else
                    (lambda: self._set_status("设备完全离线，请先打开手机无线调试或 AideLink App", "#b42318", 2000))
                )
                self._rounded_button(
                    row, "⚡安装",
                    install_cmd,
                    width=58, height=22,
                    fill="#239957" if install_enabled else "#f0f3f8",
                    outline="#239957" if install_enabled else "#e1e6ed",
                    fg="#ffffff" if install_enabled else "#b4c0d0",
                    font_size=7, bold=install_enabled, radius=8,
                ).pack(side="left", padx=(0, 4))

        self._run_api("/api/devices", on_success=render, busy_text="正在读取设备…")

    def _copy_device_address(self, device):
        """在线设备点名字 → 复制 ip:port 到剪贴板"""
        ip = device.get("online_ip") or device.get("ip")
        if not ip:
            self._set_status("设备没有可复制的 IP", "#b42318", 1800)
            return
        port = device.get("adb_port") or 5555
        address = f"{ip}:{port}"
        self.root.clipboard_clear()
        self.root.clipboard_append(address)
        self.root.update_idletasks()
        alias = device.get("alias") or ip
        self._set_status(f"已复制 {alias} 地址 {address}", "#239957", 1800)

    def _connect_device(self, device):
        """离线设备点名字 → POST /api/adb/connect 触发 enable_wireless + adb connect"""
        ip = device.get("online_ip") or device.get("ip")
        if not ip:
            self._set_status("设备没有可连接的 IP", "#b42318", 1800)
            return
        port = device.get("adb_port") or 5555
        configured_alias = device.get("alias")
        alias = configured_alias or ip
        payload = (
            {"alias": configured_alias, "timeout": 60}
            if configured_alias
            else {"ip": ip, "port": port, "timeout": 60}
        )

        def on_success(result):
            method = result.get("method", "adb_connect")
            device_id = result.get("device") or f"{ip}:{port}"
            self._set_status(
                f"✅ 已连接 {alias}（{method}）：{device_id}",
                "#239957", 2400,
            )
            # 连接成功后刷新设备列表（更新 is_adb_connected 状态）
            self._render(self.current_model)

        self._run_api(
            "/api/adb/connect", method="POST", payload=payload,
            on_success=on_success, busy_text=f"正在连接 {alias}…",
            timeout=75,
        )

    def _install_apk_to_device(self, device, force_adb_only=False):
        """[⚡安装] 按钮：串行调 /api/adb/connect + /api/adb/project-install。

        参数 force_adb_only：
            False（默认，AideLink 在线场景）→ 走完整链路：/api/adb/connect（enable_wireless + adb connect）+ project-install
            True（仅 ADB 在线、AideLink 不在线场景）→ 跳过 connect，直接 project-install（adb 已连接）
        """
        ip = device.get("online_ip") or device.get("ip")
        if not ip:
            self._set_status("设备没有 IP，无法安装", "#b42318", 1800)
            return
        port = device.get("adb_port") or 5555
        configured_alias = device.get("alias")
        alias = configured_alias or ip
        project_path = (self.current_model.get("project_path") or "").strip()
        if not project_path:
            self._set_status("当前项目未识别，无法安装", "#b42318", 1800)
            return

        def worker():
            if force_adb_only:
                # 仅 ADB 在线：跳过 connect，直接 install（/api/adb/project-install 内部会幂等 adb connect）
                device_ip = ip
                device_port = port
            else:
                # AideLink 在线：走完整 ensure_device 链路（enable_wireless + adb connect）
                connect_payload = (
                    {"alias": configured_alias, "timeout": 60}
                    if configured_alias
                    else {"ip": ip, "port": port, "timeout": 60}
                )
                try:
                    connect_resp = api_request("/api/adb/connect", method="POST", payload=connect_payload, timeout=75)
                except Exception as exc:
                    self._post_ui(lambda msg=f"[ensure_device] {exc}": self._set_status(msg, "#b42318"))
                    return
                if not connect_resp.get("ok"):
                    err = connect_resp.get("error") or "ADB 连接失败"
                    self._post_ui(lambda msg=f"[ensure_device] {alias} {err}": self._set_status(msg, "#b42318", 3000))
                    return
                device_ip = connect_resp.get("ip") or ip
                device_port = int(connect_resp.get("port") or port)

            # 安装 APK
            install_payload = {
                "ip": device_ip, "port": device_port,
                "project_path": project_path,
            }
            try:
                install_resp = api_request(
                    "/api/adb/project-install", method="POST",
                    payload=install_payload, timeout=120,
                )
            except Exception as exc:
                self._post_ui(lambda msg=f"[install] {exc}": self._set_status(msg, "#b42318"))
                return
            if not install_resp.get("ok"):
                err = install_resp.get("error") or "APK 安装失败"
                self._post_ui(lambda msg=f"[install] {alias} {err}": self._set_status(msg, "#b42318", 3000))
                return

            application_id = install_resp.get("application_id", "")
            apk_name = (install_resp.get("apk_path") or "").split("\\")[-1].split("/")[-1]
            msg = f"✅ 已安装到 {alias}"
            if application_id:
                msg += f"：{application_id}"
            if apk_name:
                msg += f" ({apk_name})"

            def on_done():
                self._set_status(msg, "#239957", 3000)
                # 安装成功后刷新列表（更新 ADB 状态）
                self._render(self.current_model)

            self._post_ui(on_done)

        self._set_status(f"正在安装到 {alias}…")
        threading.Thread(target=worker, daemon=True, name="AideLinkApkInstall").start()

    def _launch_app_service(self, device):
        """[仅 ADB 在线场景] 点设备名 → 调 /api/adb/launch-app 拉起 ConnectionService。

        通过 adb shell am start-foreground-service 启动 ConnectionService，
        App 不会切到前台，仅通过 Notification 显示运行状态；SSE 心跳自动恢复。
        """
        ip = device.get("online_ip") or device.get("ip")
        if not ip:
            self._set_status("设备没有 IP，无法拉起服务", "#b42318", 1800)
            return
        port = device.get("adb_port") or 5555
        alias = device.get("alias") or ip
        payload = {"ip": ip, "port": port, "alias": alias}

        def on_success(result):
            self._set_status(
                f"✅ 已拉起 {alias} 的 AideLink 服务，等待 SSE 心跳恢复…",
                "#239957", 4000,
            )
            # SSE 心跳恢复需要 App 进程冷启动 + ConnectionService.onCreate + SSE 建连，
            # 实测约 5-8 秒。分阶段刷新：5 秒 + 10 秒，确保能抓到状态变化。
            self.root.after(5000, lambda: self._render(self.current_model))
            self.root.after(10000, lambda: self._render(self.current_model))

        self._run_api(
            "/api/adb/launch-app", method="POST", payload=payload,
            on_success=on_success, busy_text=f"正在拉起 {alias} 的 AideLink 服务…",
        )

    def _set_alias_for_device(self, device):
        """[🏷别名] 按钮：弹输入框 → POST /api/devices/alias"""
        from tkinter import simpledialog
        ip = device.get("online_ip") or device.get("ip")
        if not ip:
            return
        port = device.get("adb_port") or 5555
        alias = simpledialog.askstring(
            "设置设备别名", f"为 {ip} 设置一个别名（例如：手机 / 平板）：",
            parent=self.root,
        )
        if not alias:
            return
        alias = alias.strip()
        if not alias:
            return

        def on_success(_result):
            self._set_status(f"已设置别名 '{alias}'", "#239957", 1800)
            self._render(self.current_model)

        self._run_api(
            "/api/devices/alias", method="POST",
            payload={"ip": ip, "alias": alias, "port": port},
            on_success=on_success, busy_text=f"正在设置别名 '{alias}'…",
        )

    @staticmethod
    def _pick_android_device(result):
        devices = result.get("devices") or []
        return next(
            (
                item for item in devices
                if item.get("is_adb_connected") or item.get("is_online") or item.get("is_active")
            ),
            devices[0] if devices else None,
        )

    def _load_android_device(self, callback, busy_text):
        def loaded(result):
            device = self._pick_android_device(result)
            if not device:
                self._set_status("没有已登记的 Android 设备", "#b42318")
                return
            callback(device)

        self._run_api("/api/devices", on_success=loaded, busy_text=busy_text)

    def connect_android(self):
        def connect(device):
            payload = {
                "alias": device.get("alias"),
                "ip": device.get("online_ip") or device.get("ip"),
                "port": device.get("adb_port") or 5555,
                "auto_enable": True,
            }
            self._run_api(
                "/api/adb/ensure",
                method="POST",
                payload=payload,
                on_success=lambda result: self._set_status(
                    result.get("message") or "ADB 已连接", "#239957", 2200
                ),
                busy_text="正在连接 ADB…",
            )

        self._load_android_device(connect, "正在读取 Android 设备…")

    def copy_android_address(self):
        def copy_address(device):
            ip = device.get("online_ip") or device.get("ip")
            port = device.get("adb_port") or 5555
            if not ip:
                self._set_status("设备没有可复制的 IP", "#b42318")
                return
            address = f"{ip}:{port}"
            self.root.clipboard_clear()
            self.root.clipboard_append(address)
            self.root.update_idletasks()
            self._set_status(f"已复制 {address}", "#239957", 1800)

        self._load_android_device(copy_address, "正在读取设备地址…")

    def android_screenshot_feedback(self, device=None):
        """通知目标设备弹出 App 端的截图反馈界面。

        通过 POST /api/adb/screenshot-feedback publish 一条 app.command 事件到目标设备，
        App 收到后启动 UiLocatorService 的截图反馈流程（截图 + 标注 + 上传到 IDE）。
        电脑端不再拉截图、不再粘贴、不再发提示词——所有操作都在手机上完成。

        参数 device：从浮窗设备列表传入的目标设备；为 None 时回退到自动挑选第一台在线设备。
        """
        ip = None
        alias = None
        if device:
            ip = device.get("online_ip") or device.get("ip")
            alias = device.get("alias")

        if not ip:
            # 没传 device 或 device 无 IP，回退到自动挑选
            def pick_and_request():
                result = api_request("/api/devices")
                picked = self._pick_android_device(result)
                if not picked:
                    self._post_ui(lambda: self._set_status("没有已登记的 Android 设备", "#b42318", 1800))
                    return
                ip_val = picked.get("online_ip") or picked.get("ip")
                if not ip_val:
                    self._post_ui(lambda: self._set_status("设备没有可用的 IP", "#b42318", 1800))
                    return
                self._do_request_screenshot_feedback(ip_val, picked.get("alias"))

            threading.Thread(target=pick_and_request, daemon=True, name="AideLinkPickDevice").start()
            return

        self._do_request_screenshot_feedback(ip, alias)

    def _do_request_screenshot_feedback(self, ip, alias=None):
        """实际调用 /api/adb/screenshot-feedback 端点。"""
        payload = {"ip": ip}
        if alias:
            payload["alias"] = alias
        if self.selected_ide_key:
            payload["target_ide"] = self.selected_ide_key
        label = alias or ip

        def on_success(result):
            self._set_status(
                f"已通知 {label} 弹出截图反馈界面，请在手机上完成标注",
                "#239957", 3000,
            )

        self._run_api(
            "/api/adb/screenshot-feedback",
            method="POST",
            payload=payload,
            on_success=on_success,
            busy_text=f"正在通知 {label} 弹出截图反馈界面…",
        )

    def refresh_web_page(self):
        self._run_api(
            "/api/floating-window/web-refresh",
            method="POST",
            payload={},
            busy_text="正在刷新浏览器页面…",
        )

    def open_web_component_locator(self):
        # 复用 web 端已完善的 Ctrl+点击组件定位模式（debug-mode.js）
        webbrowser.open(f"{BRIDGE_URL.rstrip('/')}/?debug=1")
        self._set_status("已打开 Web 组件定位模式", "#239957", 1800)

    def open_prompt_component_locator(self):
        surface = self._active_tool_surface(
            getattr(self, "current_model", {}).get("capabilities") or []
        )
        if not surface:
            self._set_status("请先在标题栏选择 Android、Web 或 Windows", "#b42318", 2200)
            return
        active_tab = getattr(self, "active_tab", "")
        current_page = active_tab if active_tab in {"create", "manage", "tools"} else ""
        page_query = f"&current_page={current_page}" if current_page else ""
        self._run_api(
            f"/api/project-map/interfaces?surface={surface}{page_query}",
            on_success=lambda result, selected_surface=surface: self._show_component_map_picker(
                selected_surface, result
            ),
            busy_text="正在读取项目界面地图…",
        )

    def _fallback_component_locator(self, surface):
        if surface == "web":
            self.open_web_component_locator()
        elif surface == "windows":
            self.windows_component_locator()
        elif surface == "android":
            self.android_screenshot_feedback()

    def _show_component_map_picker(self, surface, result):
        interfaces = result.get("interfaces") or []
        pages = interfaces[0].get("pages") if interfaces else []
        pages = sorted(
            pages or [],
            key=lambda page: not bool(page.get("is_current")),
        )
        dialog = self.tk.Toplevel(self.root)
        dialog.title("从项目界面地图选择组件")
        dialog.geometry("760x460")
        dialog.minsize(680, 380)
        dialog.configure(bg="#ffffff")
        dialog.transient(self.root)

        header = self.tk.Frame(dialog, bg="#f6f8fc")
        header.pack(fill="x")
        self.tk.Label(
            header,
            text="从项目界面地图选择",
            bg="#f6f8fc",
            fg="#182230",
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 2))
        self.tk.Label(
            header,
            text=(
                "已优先展示当前打开界面的实际可见内容；静态项目地图作为补充。"
                if any(page.get("is_current") for page in pages)
                else "未识别到当前窗口，以下为项目地图内容；需要时可使用截图定位。"
            ),
            bg="#f6f8fc",
            fg="#667085",
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", padx=14, pady=(0, 10))

        catalog = interfaces[0] if interfaces else {}
        component_types = list(catalog.get("component_types") or [])
        mode = {"value": "interface"}
        mode_row = self.tk.Frame(dialog, bg="#ffffff")
        mode_row.pack(fill="x", padx=14, pady=(10, 0))

        search_var = self.tk.StringVar()
        search = self.tk.Entry(
            dialog, textvariable=search_var, relief="solid", bd=1,
            font=("Microsoft YaHei UI", 9),
        )
        search.pack(fill="x", padx=14, pady=(8, 8), ipady=5)

        content = self.tk.Frame(dialog, bg="#ffffff")
        content.pack(fill="both", expand=True, padx=14)
        primary_column = self.tk.Frame(content, bg="#ffffff")
        primary_column.pack(side="left", fill="y", padx=(0, 8))
        primary_title = self.tk.Label(
            primary_column, text="1  选择界面", bg="#ffffff", fg="#344054",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        primary_title.pack(anchor="w", pady=(0, 4))
        primary_list = self.tk.Listbox(
            primary_column, width=19, exportselection=False, relief="solid", bd=1,
            font=("Microsoft YaHei UI", 9),
        )
        primary_list.pack(fill="y", expand=True)
        secondary_column = self.tk.Frame(content, bg="#ffffff")
        secondary_column.pack(side="left", fill="y", padx=(0, 8))
        secondary_title = self.tk.Label(
            secondary_column, text="2  选择区域", bg="#ffffff", fg="#344054",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        secondary_title.pack(anchor="w", pady=(0, 4))
        secondary_list = self.tk.Listbox(
            secondary_column, width=19, exportselection=False, relief="solid", bd=1,
            font=("Microsoft YaHei UI", 9),
        )
        secondary_list.pack(fill="y", expand=True)
        component_column = self.tk.Frame(content, bg="#ffffff")
        component_column.pack(side="left", fill="both", expand=True)
        self.tk.Label(
            component_column, text="3  选择组件（可选）", bg="#ffffff", fg="#344054",
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        component_list = self.tk.Listbox(
            component_column, exportselection=False, relief="solid", bd=1,
            font=("Microsoft YaHei UI", 9),
        )
        component_list.pack(fill="both", expand=True)

        visible_components = []
        visible_secondary = []

        def clean_name(value):
            return re.sub(r"^\[[^\]]+\]\s*", "", str(value or "")).strip()

        def selected_page():
            selection = primary_list.curselection()
            return pages[selection[0]] if selection and selection[0] < len(pages) else None

        def render_components(_event=None):
            nonlocal visible_components, visible_secondary
            query = search_var.get().strip().lower()
            primary_selection = primary_list.curselection()
            secondary_selection = secondary_list.curselection()
            candidates = []
            if mode["value"] == "interface":
                page = selected_page()
                page_components = list((page or {}).get("components") or [])
                areas = []
                for item in page_components:
                    area = str(item.get("area") or "").strip()
                    if area and area not in areas:
                        areas.append(area)
                visible_secondary = [""] + areas
                secondary_list.delete(0, "end")
                secondary_list.insert("end", "全部组件")
                for area in areas:
                    secondary_list.insert("end", area)
                selected_area = ""
                if secondary_selection and secondary_selection[0] < len(visible_secondary):
                    selected_area = visible_secondary[secondary_selection[0]]
                    secondary_list.selection_set(secondary_selection[0])
                else:
                    secondary_list.selection_set(0)
                candidates = [
                    item for item in page_components
                    if not selected_area
                    or str(item.get("area") or "") == selected_area
                    or str(item.get("area") or "").startswith(selected_area + " / ")
                ]
            else:
                type_group = (
                    component_types[primary_selection[0]]
                    if primary_selection and primary_selection[0] < len(component_types)
                    else None
                )
                type_items = list((type_group or {}).get("items") or [])
                page_names = []
                for item in type_items:
                    page_name = str(item.get("page") or "")
                    if page_name and page_name not in page_names:
                        page_names.append(page_name)
                visible_secondary = page_names
                secondary_list.delete(0, "end")
                for page_name in page_names:
                    secondary_list.insert("end", page_name)
                selected_page_name = ""
                if secondary_selection and secondary_selection[0] < len(page_names):
                    selected_page_name = page_names[secondary_selection[0]]
                    secondary_list.selection_set(secondary_selection[0])
                elif page_names:
                    selected_page_name = page_names[0]
                    secondary_list.selection_set(0)
                candidates = [
                    item for item in type_items
                    if not selected_page_name or item.get("page") == selected_page_name
                ]
            if query:
                candidates = [
                    item for item in candidates
                    if query in " ".join([
                        str(item.get("name") or ""),
                        str(item.get("area") or ""),
                        str(item.get("file") or ""),
                    ]).lower()
                ]
            visible_components = candidates
            component_list.delete(0, "end")
            for item in candidates:
                area = str(item.get("area") or "").split(" / ")[-1]
                label = clean_name(item.get("name"))
                component_list.insert("end", f"{label}  ·  {area}" if area else label)

        def render_primary():
            primary_list.delete(0, "end")
            secondary_list.delete(0, "end")
            component_list.delete(0, "end")
            if mode["value"] == "interface":
                primary_title.config(text="1  选择界面")
                secondary_title.config(text="2  选择区域")
                for page in pages:
                    page_name = page.get("name") or "未命名界面"
                    primary_list.insert(
                        "end",
                        f"● 当前  {page_name}" if page.get("is_current") else page_name,
                    )
            else:
                primary_title.config(text="1  选择组件类型")
                secondary_title.config(text="2  所属界面")
                for group in component_types:
                    primary_list.insert(
                        "end", f"{group.get('type') or '其他'} ({group.get('count', 0)})"
                    )
            if primary_list.size():
                primary_list.selection_set(0)
            render_components()

        def switch_mode(value):
            mode["value"] = value
            interface_mode_btn.config(
                bg="#0867f2" if value == "interface" else "#f2f4f7",
                fg="#ffffff" if value == "interface" else "#344054",
            )
            type_mode_btn.config(
                bg="#0867f2" if value == "type" else "#f2f4f7",
                fg="#ffffff" if value == "type" else "#344054",
            )
            render_primary()

        interface_mode_btn = self.tk.Button(
            mode_row, text="按界面", command=lambda: switch_mode("interface"),
            relief="flat", bg="#0867f2", fg="#ffffff", padx=12, pady=4,
        )
        interface_mode_btn.pack(side="left")
        type_mode_btn = self.tk.Button(
            mode_row, text="按组件类型", command=lambda: switch_mode("type"),
            relief="flat", bg="#f2f4f7", fg="#344054", padx=12, pady=4,
        )
        type_mode_btn.pack(side="left", padx=(6, 0))

        def save_target(target, status):
            self.prompt_component_name = str(target.get("name") or "")
            self.prompt_component_location = str(target.get("location") or target.get("page") or "")
            self.prompt_component_ref = {
                key: value for key, value in target.items()
                if key not in {"name", "location"}
            }
            self._add_component_target(target)
            dialog.destroy()
            self.active_tab = "create"
            self._render(self.current_model)
            self.insert_component_target(target)
            self._set_status(status, "#239957", 1800)

        def apply_location_selection(_event=None):
            page = selected_page() if mode["value"] == "interface" else None
            secondary_selection = secondary_list.curselection()
            if mode["value"] == "type":
                page_name = (
                    visible_secondary[secondary_selection[0]]
                    if secondary_selection and secondary_selection[0] < len(visible_secondary)
                    else ""
                )
                page = next(
                    (item for item in pages if item.get("name") == page_name), None
                )
            if not page:
                self._set_status("请先选择界面", "#b42318", 1600)
                return
            page_name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", str(page.get("name") or "")).strip()
            area = ""
            if mode["value"] == "interface" and secondary_selection:
                index = secondary_selection[0]
                area = visible_secondary[index] if index < len(visible_secondary) else ""
            save_target({
                "id": f"location:{surface}:{page.get('id') or page_name}:{area}",
                "surface": surface,
                "page": page_name,
                "area": area,
                "name": "",
                "location": " / ".join(part for part in (page_name, area) if part),
                "file": page.get("file", ""),
                "source": page.get("source", ""),
                "target_kind": "area" if area else "interface",
            }, "已选择界面区域" if area else "已选择整个界面")

        def apply_selection(_event=None):
            selection = component_list.curselection()
            if not selection or selection[0] >= len(visible_components):
                self._set_status("请选择组件，或直接选择界面/区域", "#b42318", 1600)
                return
            item = visible_components[selection[0]]
            page = selected_page() if mode["value"] == "interface" else None
            raw_page_name = str((page or {}).get("name") or item.get("page") or "")
            page_name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", raw_page_name).strip()
            area = str(item.get("area") or "").strip()
            location_parts = [part for part in (page_name, area) if part]
            target = {
                "id": item.get("id", ""),
                "surface": surface,
                "page": page_name,
                "area": area,
                "file": item.get("file", ""),
                "line_start": item.get("line_start", 0),
                "line_end": item.get("line_end", 0),
                "source": item.get("source", ""),
                "confidence": item.get("confidence", 0),
                "name": clean_name(item.get("name")),
                "location": " / ".join(location_parts),
            }
            save_target(target, "已从项目地图选择组件")

        render_primary()
        primary_list.bind("<<ListboxSelect>>", render_components)
        secondary_list.bind("<<ListboxSelect>>", render_components)
        component_list.bind("<Double-Button-1>", apply_selection)
        search_var.trace_add("write", lambda *_args: render_components())

        footer = self.tk.Frame(dialog, bg="#ffffff")
        footer.pack(fill="x", padx=14, pady=12)
        self.tk.Button(
            footer,
            text="地图中没有，使用截图定位",
            command=lambda: (dialog.destroy(), self._fallback_component_locator(surface)),
            relief="flat", bg="#f2f4f7", fg="#344054", padx=10, pady=6,
        ).pack(side="left")
        self.tk.Button(
            footer, text="取消", command=dialog.destroy, relief="flat",
            bg="#ffffff", fg="#475467", padx=10, pady=6,
        ).pack(side="right", padx=(8, 0))
        self.tk.Button(
            footer, text="选择界面/区域", command=apply_location_selection, relief="flat",
            bg="#eaf2ff", fg="#0867f2", padx=12, pady=6,
        ).pack(side="right", padx=(8, 0))
        self.tk.Button(
            footer, text="选择组件", command=apply_selection, relief="flat",
            bg="#0867f2", fg="#ffffff", padx=12, pady=6,
        ).pack(side="right")

    def windows_screenshot_feedback(self):
        """自由框选屏幕任意区域 → 标注 → 上传到剪贴板 → 粘贴到 IDE → 发送提示词"""
        if not self._ensure_ide_for_feedback("windows"):
            return
        self._start_region_capture(mode="feedback")

    def windows_component_locator(self):
        """框选 Windows 组件，用截图模型识别组件名称和界面位置并回填创建页。"""
        self.active_tab = "create"
        self.region_capture_mode = "component"
        self._start_region_capture(mode="component")

    def _start_region_capture(self, mode="feedback"):
        self.region_capture_mode = mode if mode in {"feedback", "component"} else "feedback"
        self._set_status(
            "请框选要识别的 Windows 组件…"
            if self.region_capture_mode == "component"
            else "正在截取屏幕…"
        )
        # 先隐藏浮窗，避免它自身出现在截图中
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(200, self._grab_and_snip)

    def _grab_and_snip(self):
        """透明框选：直接在真实屏幕上拖拽选区（不预先显示截图），
        框选落在哪块显示器就截哪块——由服务器按该显示器全屏截图后裁出选区。
        显示器枚举与截图均走 AideLink 桥接服务的 /screenshot/monitors、/screenshot/full
        接口（服务器进程已正确处理多显示器 + DPI），本进程只负责 UI。
        """
        try:
            monitors, err = _fetch_monitors()
            if err:
                self.root.deiconify()
                self._set_status(err, "#b42318")
                return
            self.root.withdraw()
            self._open_snip_overlay(monitors)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            try:
                self.root.deiconify()
            except Exception:
                pass
            self._set_status(f"截图启动失败：{exc}", "#b42318", 5000)
    def _open_snip_overlay(self, monitors):
        """半透明蒙层框选：用 -alpha 0.35 的暗色蒙层覆盖整块虚拟屏（所有显示器）。

        关键：不用 -transparentcolor（它会让透明区域点击穿透到下层窗口，整屏透明时
        点哪里都收不到事件 → 表现为"点击没反应"）。-alpha 只影响渲染、不穿透点击，
        所以整屏都能拖拽，且蒙层可见，用户能明确感知已进入框选。
        """
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = max(1, user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
        vh = max(1, user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN

        # 各显示器在「虚拟屏逻辑坐标」下的矩形（设备像素 / scale_factor）
        mon_rects = []  # (name, sf, v_left, v_top, v_w, v_h, rect)
        for m in monitors:
            l, t, r, b = m["rect"]
            sf = m.get("scale_factor") or 1.0
            if sf <= 0:
                sf = 1.0
            vl, vt = l / sf, t / sf
            vw_m, vh_m = (r - l) / sf, (b - t) / sf
            mon_rects.append((m["name"], sf, vl, vt, vw_m, vh_m, m["rect"]))

        DIM = "#0a0e14"
        ov = self.tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.35)  # 半透明蒙层：可见 + 不穿透点击
        ov.configure(bg=DIM)

        cv = self.tk.Canvas(ov, width=vw, height=vh, bg=DIM,
                            highlightthickness=0, cursor="cross")
        cv.pack()
        ov.update_idletasks()  # 确保 winfo_id() 有效、窗口已 realize

        # 用 SetWindowPos 把浮层精确摆到整块虚拟屏（支持负坐标，绕过 Tk geometry 限制）
        try:
            _set_window_rect(ov.winfo_id(), vx, vy, vw, vh)
        except Exception:
            ov.geometry(f"{vw}x{vh}+{max(0, vx)}+{max(0, vy)}")
        ov.lift()

        # 画出各显示器轮廓，提示用户边界
        for name, sf, vl, vt, vw_m, vh_m, _ in mon_rects:
            rx, ry = int(vl - vx), int(vt - vy)
            rw_, rh_ = int(vw_m), int(vh_m)
            cv.create_rectangle(rx, ry, rx + rw_ - 1, ry + rh_ - 1,
                                outline="#2da9ff", width=1, dash=(4, 3))

        instruction = (
            "拖拽框选目标组件 · 松手后自动识别 · Esc 取消"
            if getattr(self, "region_capture_mode", "feedback") == "component"
            else "拖拽选择区域 · 松手即截取 · Esc 取消"
        )
        cv.create_text(12, 12, text=instruction,
                       fill="#2da9ff", font=("Microsoft YaHei UI", 11), anchor="nw")

        sel = {"x0": None, "y0": None, "x1": None, "y1": None}

        def clamp(v, lo, hi):
            return max(lo, min(hi, v))

        def draw_selection():
            cv.delete("sel")
            if sel["x0"] is None or sel["x1"] is None:
                return
            x0 = clamp(min(sel["x0"], sel["x1"]), 0, vw)
            y0 = clamp(min(sel["y0"], sel["y1"]), 0, vh)
            x1 = clamp(max(sel["x0"], sel["x1"]), 0, vw)
            y1 = clamp(max(sel["y0"], sel["y1"]), 0, vh)
            if x1 - x0 < 2 or y1 - y0 < 2:
                return
            cv.create_rectangle(x0, y0, x1, y1, outline="#2da9ff", width=2, tags="sel")
            label_y = y1 + 16 if y1 + 16 < vh else y0 - 26
            cv.create_text(x0 + 4, label_y, text=f"{x1 - x0} x {y1 - y0}",
                           fill="#2da9ff", font=("Microsoft YaHei UI", 10), anchor="nw", tags="sel")

        def on_press(e):
            sel["x0"] = clamp(e.x, 0, vw)
            sel["y0"] = clamp(e.y, 0, vh)
            sel["x1"] = sel["x0"]
            sel["y1"] = sel["y0"]
            cv.delete("sel")

        def on_drag(e):
            sel["x1"] = clamp(e.x, 0, vw)
            sel["y1"] = clamp(e.y, 0, vh)
            draw_selection()

        def capture():
            if sel["x0"] is None or sel["x1"] is None:
                return
            x0 = clamp(min(sel["x0"], sel["x1"]), 0, vw)
            y0 = clamp(min(sel["y0"], sel["y1"]), 0, vh)
            x1 = clamp(max(sel["x0"], sel["x1"]), 0, vw)
            y1 = clamp(max(sel["y0"], sel["y1"]), 0, vh)
            if x1 - x0 < 5 or y1 - y0 < 5:
                return
            ov.destroy()
            # 选区中心落在哪块显示器，就截哪块
            cx, cy = (x0 + x1) / 2 + vx, (y0 + y1) / 2 + vy
            target = None
            for name, sf, vl, vt, vw_m, vh_m, rect in mon_rects:
                if vl <= cx <= vl + vw_m and vt <= cy <= vt + vh_m:
                    target = (name, sf, vl, vt, vw_m, vh_m, rect)
                    break
            if target is None:
                best, bd = None, 1e18
                for name, sf, vl, vt, vw_m, vh_m, rect in mon_rects:
                    dx = cx - (vl + vw_m / 2)
                    dy = cy - (vt + vh_m / 2)
                    d = dx * dx + dy * dy
                    if d < bd:
                        bd, best = d, (name, sf, vl, vt, vw_m, vh_m, rect)
                target = best
            self._capture_region(target, (x0, y0, x1, y1), (vx, vy))

        def cancel():
            ov.destroy()
            self.root.deiconify()
            self.refresh()

        cv.bind("<ButtonPress-1>", on_press)
        cv.bind("<B1-Motion>", on_drag)
        cv.bind("<ButtonRelease-1>", lambda _e: capture())
        cv.bind("<Escape>", lambda _e: cancel())
        ov.bind("<Escape>", lambda _e: cancel())

        ov.focus_set()
    def _capture_region(self, mon, box, vorigin):
        """确认框选后：调用服务器截取该显示器全屏，按框选的（虚拟屏逻辑）坐标裁出选区，进入标注。

        框选坐标来自覆盖整块虚拟屏的透明浮层（本进程非 DPI 感知，坐标为逻辑像素），
        用「返回图实际尺寸 / 该显示器逻辑宽高」换算回图像像素，天然兼容 DPI 缩放与
        服务器端的 _scale_for_phone 下采样。
        """
        self._set_status("正在截取所选区域…")
        name, sf, vl, vt, vw_m, vh_m, rect = mon
        x0, y0, x1, y1 = box
        vx, vy = vorigin
        # 框选相对该显示器逻辑左上角的偏移，并夹紧到显示器范围内
        rx0 = max(0, min(vw_m, x0 - (vl - vx)))
        ry0 = max(0, min(vh_m, y0 - (vt - vy)))
        rx1 = max(0, min(vw_m, x1 - (vl - vx)))
        ry1 = max(0, min(vh_m, y1 - (vt - vy)))
        url = f"{BRIDGE_URL.rstrip('/')}/screenshot/full?monitor={quote(name)}"
        try:
            raw = http_get_bytes(url, timeout=20)
        except Exception as exc:
            self.root.deiconify()
            self._set_status(f"截图失败：{exc}", "#b42318")
            return
        if not raw:
            self.root.deiconify()
            self._set_status("截图失败：未获取到屏幕图像", "#b42318")
            return
        try:
            screen = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            self.root.deiconify()
            self._set_status(f"截图解码失败：{exc}", "#b42318")
            return
        iw, ih = screen.size
        # 逻辑宽高 -> 图像像素 的比例（含 DPI 与 _scale_for_phone 下采样）
        sx = iw / vw_m if vw_m else 1.0
        sy = ih / vh_m if vh_m else 1.0
        bx0 = max(0, min(iw, int(round(rx0 * sx))))
        by0 = max(0, min(ih, int(round(ry0 * sy))))
        bx1 = max(0, min(iw, int(round(rx1 * sx))))
        by1 = max(0, min(ih, int(round(ry1 * sy))))
        if bx1 - bx0 < 2 or by1 - by0 < 2:
            self.root.deiconify()
            self._set_status("选区过小，已取消", "#b42318", 2000)
            return
        if getattr(self, "region_capture_mode", "feedback") == "component":
            component_image = self._prepare_windows_component_image(
                screen, (bx0, by0, bx1, by1)
            )
            self.root.deiconify()
            self._recognize_windows_component(
                component_image,
                selection_hint={
                    "selected_box": [bx0, by0, bx1, by1],
                    "screen_size": [iw, ih],
                },
            )
            return
        cropped = screen.crop((bx0, by0, bx1, by1)).convert("RGB")
        self._open_annotate_editor(cropped, (0, 0, cropped.width, cropped.height))

    @staticmethod
    def _prepare_windows_component_image(screen, box):
        """保留组件周边上下文，并用红框明确用户实际选择的目标。"""
        bx0, by0, bx1, by1 = box
        selected_width = max(1, bx1 - bx0)
        selected_height = max(1, by1 - by0)
        pad_x = max(80, int(selected_width * 0.55))
        pad_y = max(60, int(selected_height * 0.8))
        cx0 = max(0, bx0 - pad_x)
        cy0 = max(0, by0 - pad_y)
        cx1 = min(screen.width, bx1 + pad_x)
        cy1 = min(screen.height, by1 + pad_y)
        context = screen.crop((cx0, cy0, cx1, cy1)).convert("RGB")
        draw = ImageDraw.Draw(context)
        outline_width = max(3, min(8, round(min(context.size) / 120)))
        draw.rectangle(
            (bx0 - cx0, by0 - cy0, bx1 - cx0, by1 - cy0),
            outline="#ff2d2d",
            width=outline_width,
        )
        return context

    @staticmethod
    def _selection_location_hint(selection_hint):
        selected = (selection_hint or {}).get("selected_box") or []
        screen_size = (selection_hint or {}).get("screen_size") or []
        if len(selected) != 4 or len(screen_size) != 2:
            return "Windows 界面中的已框选位置"
        width, height = screen_size
        if not width or not height:
            return "Windows 界面中的已框选位置"
        center_x = (selected[0] + selected[2]) / 2 / width
        center_y = (selected[1] + selected[3]) / 2 / height
        horizontal = "左侧" if center_x < 0.34 else "右侧" if center_x > 0.66 else "中部"
        vertical = "顶部" if center_y < 0.34 else "底部" if center_y > 0.66 else "中部"
        return f"Windows 界面{vertical}{horizontal}"

    def _component_prompt_payload(self, image_ref, selection_hint=None):
        category = getattr(self, "prompt_task_type", "unspecified")
        compose_type = PROMPT_CATEGORY_TO_COMPOSE_TYPE.get(category, "auto")
        return {
            "user_text": "【用户未描述具体需求】",
            "task_type": compose_type,
            "category": category,
            "image": image_ref,
            "component": {
                "platform": "Windows",
                "name": "红框内目标组件",
                "location": self._selection_location_hint(selection_hint),
                "technical": selection_hint or {},
            },
        }

    def _recognize_windows_component(self, component_image, selection_hint=None):
        output = io.BytesIO()
        component_image.save(output, "PNG")
        png_bytes = output.getvalue()
        self._set_status("正在识别框选组件和界面位置…")

        def worker():
            try:
                uploaded = http_post_multipart(
                    f"{BRIDGE_URL.rstrip('/')}/upload",
                    fields={"to_clipboard": "false"},
                    files={
                        "file": (
                            f"component_locator_{int(time.time())}.png",
                            png_bytes,
                            "image/png",
                        )
                    },
                )
                if not uploaded.get("ok"):
                    raise RuntimeError(uploaded.get("raw") or "组件截图上传失败")
                image_ref = uploaded.get("url") or uploaded.get("path")
                result = api_request(
                    "/api/prompt/compose",
                    method="POST",
                    payload=self._component_prompt_payload(image_ref, selection_hint),
                    timeout=60,
                )
                if not result.get("ok"):
                    raise RuntimeError(result.get("message") or "组件识别失败")
            except Exception as exc:
                self._post_ui(
                    lambda message=str(exc): self._set_status(
                        f"组件识别失败：{message}", "#b42318", 4000
                    )
                )
                return
            self._post_ui(
                lambda data=result, hint=selection_hint, ref=image_ref: self._apply_windows_component_result(
                    data, hint, ref
                )
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="AideLinkWindowsComponentLocator",
        ).start()

    def _apply_windows_component_result(self, result, selection_hint=None, image_ref=None):
        image_used = bool(result.get("image_used"))
        recognized_name = str(result.get("component_name") or "").strip()
        recognized_location = str(result.get("component_location") or "").strip()
        generic_names = {"所选组件", "红框内目标组件"}
        if image_used and recognized_name not in generic_names:
            self.prompt_component_name = recognized_name
        elif not getattr(self, "prompt_component_name", ""):
            self.prompt_component_name = "已框选组件"
        if image_used and recognized_location:
            self.prompt_component_location = recognized_location
        else:
            self.prompt_component_location = self._selection_location_hint(selection_hint)
        if image_used and self.prompt_component_name:
            learned_component = {
                "name": self.prompt_component_name,
                "page": self.prompt_component_location or "截图识别组件",
                "area": self.prompt_component_location,
                "description": "由 Aide 结合截图识别并沉淀",
                "source": "screenshot",
                "confidence": 0.68,
                "bounds": selection_hint,
                "image_ref": image_ref or "",
            }
            self.prompt_component_ref = {
                "surface": "windows",
                "page": learned_component["page"],
                "area": learned_component["area"],
                "source": "screenshot",
                "confidence": learned_component["confidence"],
            }
            self._add_component_target({
                **self.prompt_component_ref,
                "name": self.prompt_component_name,
                "location": self.prompt_component_location,
            })
            threading.Thread(
                target=lambda: api_request(
                    "/api/project-map/learn-component",
                    method="POST",
                    payload={"surface": "windows", "component": learned_component},
                    timeout=30,
                ),
                daemon=True,
                name="AideLinkLearnWindowsComponent",
            ).start()
        self._schedule_input_draft_save()
        self._render(self.current_model)
        if image_used:
            self._set_status("已识别组件并回填名称与界面位置", "#239957", 2600)
        else:
            self._set_status(
                "截图模型暂不可用，已回填框选位置，请补充组件名称",
                "#b06b00",
                3200,
            )

    def _open_annotate_editor(self, source_img, bbox):
        """标注编辑器：在框选区域内绘制矩形/箭头/画笔/文字，完成后烧录并发送。"""
        cropped = source_img.crop(bbox).convert("RGB")
        cw, ch = cropped.size
        max_w, max_h = 1000, 660
        scale = min(max_w / cw, max_h / ch, 1.0)
        disp_w, disp_h = max(1, int(cw * scale)), max(1, int(ch * scale))

        editor = self.tk.Toplevel(self.root)
        editor.title("标注截图反馈")
        editor.attributes("-topmost", True)
        editor.resizable(False, False)
        editor.geometry(f"{disp_w + 28}x{disp_h + 116}")

        state = {"tool": "rect", "color": "#ff3b30"}
        ops = []
        temp_op = [None]
        width_var = self.tk.StringVar(value="4")

        toolbar = self.tk.Frame(editor, bg="#f4f6fa")
        toolbar.pack(side="top", fill="x", padx=6, pady=6)

        note_var = self.tk.StringVar(value="可选备注，会附在发送内容里")
        note_entry = self.tk.Entry(
            toolbar, textvariable=note_var, relief="solid", bd=1,
            font=("Microsoft YaHei UI", 9), fg="#9aa3b2",
        )
        note_entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)

        def on_note_focus(_e):
            if note_var.get() == "可选备注，会附在发送内容里":
                note_entry.delete(0, "end")
                note_var.set("")
                note_entry.config(fg="#1f2430")

        note_entry.bind("<FocusIn>", on_note_focus)

        canvas = self.tk.Canvas(
            editor, width=disp_w, height=disp_h, bg="#ffffff",
            highlightthickness=1, highlightbackground="#d7dce5",
        )
        canvas.pack(padx=8, pady=(0, 8))

        self._anno_base_img = ImageTk.PhotoImage(cropped.resize((disp_w, disp_h)))
        canvas.create_image(0, 0, image=self._anno_base_img, anchor="nw", tags="base")

        tool_buttons = {}

        def set_tool(name):
            state["tool"] = name
            for n, btn in tool_buttons.items():
                active = n == name
                btn.config(
                    relief="sunken" if active else "flat",
                    bg="#0867f2" if active else "#ffffff",
                    fg="#ffffff" if active else "#526078",
                )

        def cur_width():
            try:
                return max(1, int(width_var.get()))
            except Exception:
                return 4

        def _draw_op(op):
            t = op["type"]
            w = max(1, int(op["width"] * scale))
            if t == "rect":
                canvas.create_rectangle(
                    op["x0"] * scale, op["y0"] * scale, op["x1"] * scale, op["y1"] * scale,
                    outline=op["color"], width=w, tags="op",
                )
            elif t == "arrow":
                x0, y0, x1, y1 = op["x0"] * scale, op["y0"] * scale, op["x1"] * scale, op["y1"] * scale
                canvas.create_line(
                    x0, y0, x1, y1, fill=op["color"], width=w, arrow="last",
                    arrowshape=(max(8, int(w * 3)), max(8, int(w * 3)), max(4, int(w * 2))),
                    tags="op",
                )
            elif t == "pen":
                pts = [(px * scale, py * scale) for (px, py) in op["points"]]
                canvas.create_line(
                    pts, fill=op["color"], width=w, capstyle="round",
                    joinstyle="round", smooth=True, tags="op",
                )
            elif t == "text":
                canvas.create_text(
                    op["x"] * scale, op["y"] * scale, text=op["text"], fill=op["color"],
                    font=("Microsoft YaHei UI", max(12, int(op["width"] * scale * 3))),
                    anchor="nw", tags="op",
                )

        def redraw():
            canvas.delete("op")
            for op in ops:
                _draw_op(op)
            if temp_op[0] is not None:
                _draw_op(temp_op[0])

        drawing = {"active": False, "start": None, "pts": []}

        def to_img(x, y):
            return (x / scale, y / scale)

        def on_press(e):
            ix, iy = to_img(e.x, e.y)
            tool = state["tool"]
            if tool in ("rect", "arrow"):
                drawing["active"] = True
                drawing["start"] = (ix, iy)
                temp_op[0] = {
                    "type": tool, "x0": ix, "y0": iy, "x1": ix, "y1": iy,
                    "color": state["color"], "width": cur_width(),
                }
            elif tool == "pen":
                drawing["active"] = True
                drawing["pts"] = [(ix, iy)]
                temp_op[0] = {"type": "pen", "points": list(drawing["pts"]),
                              "color": state["color"], "width": cur_width()}
            elif tool == "text":
                from tkinter import simpledialog
                txt = simpledialog.askstring("文字标注", "输入标注文字：", parent=editor)
                if txt:
                    ops.append({"type": "text", "x": ix, "y": iy, "text": txt,
                                "color": state["color"], "width": cur_width()})
                    redraw()

        def on_drag(e):
            if not drawing["active"]:
                return
            ix, iy = to_img(e.x, e.y)
            if state["tool"] in ("rect", "arrow"):
                s = drawing["start"]
                temp_op[0] = {"type": state["tool"], "x0": s[0], "y0": s[1], "x1": ix, "y1": iy,
                              "color": state["color"], "width": cur_width()}
            elif state["tool"] == "pen":
                drawing["pts"].append((ix, iy))
                temp_op[0] = {"type": "pen", "points": list(drawing["pts"]),
                              "color": state["color"], "width": cur_width()}
            redraw()

        def on_release(e):
            if not drawing["active"]:
                return
            ix, iy = to_img(e.x, e.y)
            tool = state["tool"]
            if tool in ("rect", "arrow"):
                s = drawing["start"]
                ops.append({"type": tool, "x0": s[0], "y0": s[1], "x1": ix, "y1": iy,
                            "color": state["color"], "width": cur_width()})
            elif tool == "pen":
                ops.append({"type": "pen", "points": list(drawing["pts"]),
                            "color": state["color"], "width": cur_width()})
            drawing["active"] = False
            temp_op[0] = None
            redraw()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        for name, label in (("rect", "矩形"), ("arrow", "箭头"), ("pen", "画笔"), ("text", "文字")):
            btn = self.tk.Button(
                toolbar, text=label, width=5, relief="flat", bg="#ffffff", fg="#526078",
                font=("Microsoft YaHei UI", 9), command=lambda n=name: set_tool(n),
            )
            btn.pack(side="left", padx=2)
            tool_buttons[name] = btn
        set_tool("rect")

        def pick_color():
            from tkinter import colorchooser
            chosen = colorchooser.askcolor(parent=editor, initialcolor=state["color"])
            if chosen and chosen[1]:
                state["color"] = chosen[1]
                color_btn.config(bg=chosen[1])

        color_btn = self.tk.Button(
            toolbar, text="颜色", width=5, relief="flat", bg=state["color"],
            font=("Microsoft YaHei UI", 9), command=pick_color,
        )
        color_btn.pack(side="left", padx=2)

        width_menu = self.tk.OptionMenu(toolbar, width_var, "2", "4", "6", "10")
        width_menu.config(width=3, relief="flat", font=("Microsoft YaHei UI", 9))
        width_menu.pack(side="left", padx=2)

        def undo():
            if ops:
                ops.pop()
                redraw()

        def clear_all():
            ops.clear()
            redraw()

        def cancel():
            editor.destroy()
            self.root.deiconify()
            self.refresh()

        def done():
            note = note_var.get()
            if note == "可选备注，会附在发送内容里":
                note = ""
            png = self._burn_annotations(cropped, ops)
            editor.destroy()
            self.root.deiconify()
            self._send_region_feedback(png, note)

        self.tk.Button(toolbar, text="撤销", width=4, command=undo, relief="flat",
                       font=("Microsoft YaHei UI", 9)).pack(side="left", padx=2)
        self.tk.Button(toolbar, text="清空", width=4, command=clear_all, relief="flat",
                       font=("Microsoft YaHei UI", 9)).pack(side="left", padx=2)
        self.tk.Button(toolbar, text="取消", width=4, command=cancel, relief="flat",
                       bg="#fff3f3", fg="#d92d36", font=("Microsoft YaHei UI", 9)).pack(side="right", padx=2)
        self.tk.Button(toolbar, text="完成", width=4, command=done, relief="flat",
                       bg="#0867f2", fg="#ffffff", font=("Microsoft YaHei UI", 9)).pack(side="right", padx=2)

    def _burn_annotations(self, base_img, ops):
        """把标注烧录进位图，返回 PNG 字节。"""
        import math

        out = base_img.copy()
        d = ImageDraw.Draw(out)
        for op in ops:
            t = op["type"]
            color = op["color"]
            w = max(1, int(op["width"]))
            if t == "rect":
                d.rectangle([op["x0"], op["y0"], op["x1"], op["y1"]], outline=color, width=w)
            elif t == "arrow":
                x0, y0, x1, y1 = op["x0"], op["y0"], op["x1"], op["y1"]
                d.line([(x0, y0), (x1, y1)], fill=color, width=w)
                ang = math.atan2(y1 - y0, x1 - x0)
                hl = max(8, w * 3)
                a1 = ang + math.radians(150)
                a2 = ang - math.radians(150)
                d.line([(x1, y1), (x1 + hl * math.cos(a1), y1 + hl * math.sin(a1))],
                       fill=color, width=w)
                d.line([(x1, y1), (x1 + hl * math.cos(a2), y1 + hl * math.sin(a2))],
                       fill=color, width=w)
            elif t == "pen":
                d.line(op["points"], fill=color, width=w, joint="curve")
            elif t == "text":
                try:
                    font = ImageFont.truetype("msyh.ttc", max(14, w * 3))
                except Exception:
                    font = ImageFont.load_default()
                d.text((op["x"], op["y"]), op["text"], fill=color, font=font)
        buf = io.BytesIO()
        out.save(buf, "PNG")
        return buf.getvalue()

    def _send_region_feedback(self, png_bytes, note):
        if not png_bytes:
            self.refresh()
            return

        def step_upload(ctx):
            filename = f"region_feedback_{int(time.time())}.png"
            result = http_post_multipart(
                f"{BRIDGE_URL.rstrip('/')}/upload",
                fields={"to_clipboard": "true"},
                files={"file": (filename, png_bytes, "image/png")},
            )
            if not result.get("ok"):
                return False, result.get("raw") or "上传截图到剪贴板失败"
            return True, ""

        if note and note.strip():
            text = f"【截图反馈 · 标注】{note.strip()}"
        else:
            text = "【截图反馈 · 标注】请查看标注截图，结合画面分析问题"
        self._run_screenshot_feedback_flow(
            [("上传到剪贴板", step_upload)],
            busy_text="正在发送标注截图反馈",
            final_text=text,
        )

    def locate_windows_target(self):
        # 复用 web 端已完善的 IDE 校准流程（最大化 + 截图 + 拖框保存）
        if not self.selected_ide_key:
            self._set_status("请先选择一个 IDE", "#b42318", 1800)
            return
        webbrowser.open(
            f"{BRIDGE_URL.rstrip('/')}/?calibrate={quote(self.selected_ide_key)}"
        )
        self._set_status("已打开 IDE 校准页面", "#239957", 1800)

    def _ensure_ide_for_feedback(self, surface):
        if not self.selected_ide_key:
            self._set_status(f"请先选择运行中的 IDE 来接收{surface} 截图反馈", "#b42318", 2200)
            return False
        return True

    def _run_screenshot_feedback_flow(self, steps, busy_text="正在发送截图反馈", final_text=None, send_prompt=True):
        """串行执行截图反馈的前置步骤（截图 + 上传到剪贴板），最后统一粘贴到 IDE。

        steps: [(step_name, callable(ctx) -> (ok, message)), ...]
        final_text: 发送时附带的提示词；为 None 时使用默认文案。
        send_prompt: 是否在粘贴截图后发送一句提示词到 IDE。
            Android 设备行的 [📷] 按钮传 False（截图已粘贴，无需多发一句话）；
            Windows 标注反馈传 True（需要文字说明标注内容）。
        """
        self._set_status(busy_text)

        def worker():
            ctx = {"ide": self.selected_ide_key}
            for step_name, step in steps:
                self._post_ui(
                    lambda desc=step_name, base=busy_text: self._set_status(f"{base}（{desc}）")
                )
                try:
                    ok, message = step(ctx)
                except Exception as exc:
                    err = f"{step_name}失败：{exc}"
                    self._post_ui(lambda msg=err: self._set_status(msg, "#b42318"))
                    return
                if not ok:
                    err = message or f"{step_name}失败"
                    self._post_ui(lambda msg=err: self._set_status(msg, "#b42318"))
                    return

            def step_inject(ctx):
                result = api_request(
                    "/inject-clipboard", method="POST", payload={"target": ctx["ide"]}
                )
                if not result.get("ok"):
                    return False, result.get("error") or "粘贴到 IDE 失败"
                return True, ""

            def step_send(ctx):
                payload = {
                    "text": final_text if final_text is not None else "【截图反馈】请查看截图，结合画面分析问题",
                    "target": ctx["ide"],
                }
                result = api_request("/send", method="POST", payload=payload)
                if not result.get("ok"):
                    return False, result.get("raw") or "发送提示词失败"
                return True, ""

            final_steps = [("粘贴到 IDE", step_inject)]
            if send_prompt:
                final_steps.append(("发送提示词", step_send))
            for step_name, step in final_steps:
                self._post_ui(
                    lambda desc=step_name, base=busy_text: self._set_status(f"{base}（{desc}）")
                )
                try:
                    ok, message = step(ctx)
                except Exception as exc:
                    err = f"{step_name}失败：{exc}"
                    self._post_ui(lambda msg=err: self._set_status(msg, "#b42318"))
                    return
                if not ok:
                    err = message or f"{step_name}失败"
                    self._post_ui(lambda msg=err: self._set_status(msg, "#b42318"))
                    return

            self._post_ui(lambda: self._set_status("截图反馈已发送到 IDE", "#239957", 2200))
            self._post_ui(self.refresh)

        threading.Thread(
            target=worker,
            daemon=True,
            name="AideLinkFloatingWindowFeedback",
        ).start()

    def _render_codex_quota(self, quota):
        self.quota_canvas.delete("all")
        remaining = quota.get("remaining_percent")
        if not quota.get("available") or not isinstance(remaining, (int, float)):
            self.quota_canvas.create_rectangle(0, 2, 40, 6, fill="#e5e9ef", outline="")
            self.quota_label.config(text="--%", fg="#8a94a6")
            return
        remaining = max(0, min(100, round(remaining)))
        self.quota_canvas.create_rectangle(0, 2, 40, 6, fill="#e5e9ef", outline="")
        self.quota_canvas.create_rectangle(
            0, 2, round(40 * remaining / 100), 6, fill="#2fb66d", outline=""
        )
        self.quota_label.config(text=f"{remaining}%", fg="#239957")

    def _on_quota_click(self, _event):
        """点击额度条时获取 Codex 额度。拖拽时不触发。"""
        if getattr(self, "drag_moved", False):
            return
        if getattr(self, "_quota_fetching", False):
            return
        self._quota_fetching = True
        self.quota_label.config(text="···", fg="#8a94a6")

        def worker():
            try:
                resp = api_request("api/codex/quota?force=1", timeout=10)
                quota = resp.get("quota") or {}
            except Exception:
                quota = {}
            self.root.after(0, lambda: self._on_quota_fetched(quota))

        threading.Thread(target=worker, daemon=True, name="AideLinkQuotaFetch").start()

    def _on_quota_fetched(self, quota):
        self._quota_fetching = False
        self._render_codex_quota(quota)

    def _maybe_fetch_quota_on_startup(self):
        """浮窗启动且首次连接成功后获取一次额度；10 分钟内重启不重复获取。"""
        try:
            last = 0.0
            if QUOTA_LAST_FETCH_FILE.exists():
                data = json.loads(QUOTA_LAST_FETCH_FILE.read_text(encoding="utf-8"))
                last = float(data.get("last_fetch_at") or 0.0)
        except (OSError, ValueError, json.JSONDecodeError):
            last = 0.0
        if (time.time() - last) < QUOTA_STARTUP_FETCH_INTERVAL:
            return

        def worker():
            try:
                resp = api_request("api/codex/quota?force=1", timeout=10)
                quota = resp.get("quota") or {}
            except Exception:
                quota = {}
            try:
                QUOTA_LAST_FETCH_FILE.parent.mkdir(parents=True, exist_ok=True)
                QUOTA_LAST_FETCH_FILE.write_text(
                    json.dumps({"last_fetch_at": time.time()}), encoding="utf-8"
                )
            except OSError:
                pass
            self.root.after(0, lambda: self._render_codex_quota(quota))

        threading.Thread(target=worker, daemon=True, name="AideLinkQuotaStartup").start()

    def select_ide(self, key):
        self.selected_ide_key = key
        self._render(self.current_model)

    def select_tab(self, tab):
        if tab not in {"create", "manage", "tools"}:
            return
        self.active_tab = tab
        self._render(self.current_model)

    def select_prompt_task_type(self, task_type):
        if task_type not in {key for key, _label in PROMPT_TASK_TYPES}:
            return
        self.prompt_task_type = task_type
        self.prompt_candidates = []
        self._schedule_input_draft_save()
        self._render(self.current_model)

    def select_prompt_candidate(self, index):
        candidates = getattr(self, "prompt_candidates", []) or []
        if not 0 <= index < len(candidates):
            return
        prompt = str(candidates[index].get("prompt") or "").strip()
        if not prompt:
            return
        self._set_input_text(prompt)
        self._set_status("已选择智能提示词，可继续编辑", "#239957", 1800)
        self.input_box.focus_set()

    def toggle_task_more(self, task_id):
        self.expanded_task_id = None if self.expanded_task_id == task_id else task_id
        self._render(self.current_model)

    def toggle_group(self, group_name):
        if group_name in self.collapsed_groups:
            self.collapsed_groups.remove(group_name)
        else:
            self.collapsed_groups.add(group_name)
        self._render(self.current_model)

    def toggle_test_selection(self, task_id):
        if not task_id:
            return
        if task_id in self.selected_test_task_ids:
            self.selected_test_task_ids.remove(task_id)
        else:
            self.selected_test_task_ids.add(task_id)
        self._render(self.current_model)

    def toggle_test_selection_mode(self):
        self.test_selection_mode = not self.test_selection_mode
        if self.test_selection_mode:
            self.collapsed_groups.discard("待测试")
        else:
            self.selected_test_task_ids.clear()
        self._render(self.current_model)

    def dispatch_selected_tests(self):
        task_ids = [
            task.get("task_id") for task in self.current_model.get("tasks", [])
            if task.get("task_id") in self.selected_test_task_ids
        ]
        if not task_ids:
            return
        if not self.selected_ide_key:
            self._set_status("请先选择用于测试的运行中 IDE", "#b42318")
            return
        self._run_api(
            "/api/tasks/test",
            method="POST",
            payload={"task_ids": task_ids, "test_ide": self.selected_ide_key},
            on_success=lambda result: (
                self.selected_test_task_ids.clear(),
                setattr(self, "test_selection_mode", False),
                self._set_status(
                    f"已提交 {int(result.get('count') or len(task_ids))} 条排队测试",
                    "#239957", 1800,
                ),
                self.refresh(),
            ),
            busy_text="正在提交排队测试…",
        )

    def show_more_completed(self):
        self.completed_display_limit += 5
        self._render(self.current_model)

    def toggle_input_expanded(self):
        self._set_input_expanded(not self.input_expanded)
        self.input_box.focus_set()

    def _set_input_expanded(self, expanded):
        self.input_expanded = bool(expanded)
        target_height = 120 if self.input_expanded else 58
        self.input_shell.config(height=target_height)

    def _auto_expand_input(self, _event=None):
        self.input_expand_after_id = None
        if self.input_expanded:
            return
        try:
            display_lines = self.input_box.count("1.0", "end-1c", "displaylines")
            line_count = int(display_lines[0]) + 1 if display_lines else 1
        except (self.tk.TclError, TypeError, ValueError):
            line_count = self.input_box.get("1.0", "end-1c").count("\n") + 1
        if line_count >= 2:
            self._set_input_expanded(True)

    def _schedule_auto_expand(self, _event=None):
        self._schedule_input_draft_save()
        if self.input_expanded:
            return
        if self.input_expand_after_id is not None:
            self.root.after_cancel(self.input_expand_after_id)
        self.input_expand_after_id = self.root.after(120, self._auto_expand_input)

    def _handle_input_return(self, event):
        if event.state & 0x0004:
            return self._insert_input_newline()
        if self.active_tab == "create":
            self.create_task()
            return "break"
        return None

    def _handle_input_ctrl_return(self, _event):
        if self.active_tab != "create":
            return None
        return self._insert_input_newline()

    def _handle_input_undo(self, _event):
        try:
            self.input_box.edit_undo()
        except self.tk.TclError:
            pass
        self.root.after_idle(self._schedule_auto_expand)
        return "break"

    def _on_task_scroll(self, event):
        x, y = self.root.winfo_pointerxy()
        left, top = self.task_canvas.winfo_rootx(), self.task_canvas.winfo_rooty()
        if not (
            left <= x < left + self.task_canvas.winfo_width()
            and top <= y < top + self.task_canvas.winfo_height()
        ):
            return None
        units = -1 if event.delta > 0 else 1
        self.task_canvas.yview_scroll(units * 3, "units")
        return "break"

    def _insert_input_newline(self):
        self.input_box.insert("insert", "\n")
        self.root.after_idle(self._auto_expand_input)
        return "break"

    def _input_text(self):
        value = self.input_box.get("1.0", "end-1c").strip()
        return "" if value == INPUT_HINT else value

    def _set_input_text(self, value):
        try:
            self.input_box.edit_separator()
        except self.tk.TclError:
            pass
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", value)
        try:
            self.input_box.edit_separator()
        except self.tk.TclError:
            pass
        if not value:
            self._set_input_expanded(False)
        else:
            self.root.after_idle(self._auto_expand_input)
        self.input_box.config(fg="#172033")
        self._update_counter()
        self._schedule_input_draft_save()

    def _set_status(self, message, color="#657084", clear_after=0):
        self.status_detail = message
        if message:
            self.status_label.config(text=message, fg=color, cursor="hand2")
            self.status_label.bind("<Button-1>", self._copy_status_detail)
            if not self.status_label.winfo_manager():
                self.status_label.pack(fill="x", pady=(4, 0))
        else:
            self.status_label.unbind("<Button-1>")
            self.status_label.config(cursor="")
            self.status_label.pack_forget()
        if clear_after:
            self.root.after(clear_after, lambda: self._set_status(""))

    def _copy_status_detail(self, _event=None):
        if not self.status_detail:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.status_detail)
        self.root.update_idletasks()
        original = self.status_label.cget("text")
        self.status_label.config(text="已复制到剪贴板", fg="#239957")
        self.root.after(1800, lambda: self.status_label.config(text=original, fg="#657084"))

    def _post_ui(self, callback):
        self.ui_callbacks.put(callback)

    def _drain_ui_callbacks(self):
        while True:
            try:
                callback = self.ui_callbacks.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except self.tk.TclError:
                return
        self.root.after(25, self._drain_ui_callbacks)

    def _run_api(self, path, method="GET", payload=None, on_success=None, busy_text="处理中…", timeout=15):
        self._set_status(busy_text)

        def worker():
            try:
                result = api_request(path, method=method, payload=payload, timeout=timeout)
            except Exception as exc:
                message = str(exc)
                self._post_ui(lambda value=message: self._set_status(f"操作失败：{value}", "#b42318"))
                return

            def finish():
                ok = result.get("ok", result.get("success", True))
                if not ok:
                    self._set_status(result.get("message") or result.get("error") or "操作失败", "#b42318")
                    return
                if on_success:
                    on_success(result)
                else:
                    self._set_status(result.get("message") or "操作成功", "#239957", 1800)

            self._post_ui(finish)

        threading.Thread(target=worker, daemon=True, name="AideLinkFloatingWindowApi").start()

    def _send_text(self, text, clear_input=False):
        """直接发送文本到选中的 IDE"""
        if not text:
            self._set_status("请输入要发送的内容", "#b42318", 1800)
            return
        if not self.selected_ide_key:
            self._set_status("暂无可用 IDE", "#b42318", 1800)
            return

        def sent(result):
            if clear_input:
                self._set_input_text("")
            self._set_status(result.get("raw") or "已发送", "#239957", 2200)
            self.refresh()

        self._run_api(
            "/send",
            method="POST",
            payload={"text": text, "target": self.selected_ide_key},
            on_success=sent,
            busy_text=f"正在发送到 {self.selected_ide_key}…",
        )

    def _send_input(self):
        text = self._input_text()
        self._send_text(text, clear_input=True)

    def show_composer_menu(self):
        self.show_quick_reply_menu()

    def show_quick_reply_menu(self):
        menu = self.tk.Menu(self.root, tearoff=False)
        for reply in self._load_quick_replies():
            menu.add_command(label=reply, command=lambda value=reply: self._send_text(value))
        if menu.index("end") is not None:
            menu.add_separator()
        menu.add_command(label="管理快捷回复…", command=self.manage_quick_replies)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    @staticmethod
    def _load_quick_replies():
        try:
            values = json.loads(QUICK_REPLIES_FILE.read_text(encoding="utf-8"))
            replies = [str(value).strip() for value in values if str(value).strip()]
            return replies
        except (OSError, TypeError, ValueError):
            return list(DEFAULT_QUICK_REPLIES)

    @staticmethod
    def _save_quick_replies(replies):
        QUICK_REPLIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUICK_REPLIES_FILE.write_text(
            json.dumps(list(replies), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def manage_quick_replies(self):
        dialog = self.tk.Toplevel(self.root)
        dialog.title("管理快捷回复")
        dialog.geometry("330x300")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        entry_row = self.tk.Frame(dialog, bg="#ffffff")
        entry_row.pack(fill="x", padx=12, pady=(12, 8))
        entry = self.tk.Entry(entry_row, relief="solid", bd=1, font=("Microsoft YaHei UI", 9))
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        listbox = self.tk.Listbox(dialog, relief="solid", bd=1, font=("Microsoft YaHei UI", 9), activestyle="none")
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def reload_list():
            listbox.delete(0, "end")
            for reply in self._load_quick_replies():
                listbox.insert("end", reply)

        def add_reply():
            value = entry.get().strip()
            replies = self._load_quick_replies()
            if value and value not in replies:
                replies.append(value)
                self._save_quick_replies(replies)
                entry.delete(0, "end")
                reload_list()

        def remove_reply():
            selection = listbox.curselection()
            if not selection:
                return
            replies = self._load_quick_replies()
            index = selection[0]
            if index < len(replies):
                replies.pop(index)
                self._save_quick_replies(replies)
                reload_list()

        self.tk.Button(entry_row, text="添加", command=add_reply, relief="flat", bg="#0867f2", fg="#ffffff", padx=10, pady=4).pack(side="left", padx=(8, 0))
        self.tk.Button(dialog, text="删除选中", command=remove_reply, relief="flat", bg="#fff3f3", fg="#d92d36", padx=10, pady=4).pack(anchor="e", padx=12, pady=(0, 10))
        entry.bind("<Return>", lambda _event: (add_reply(), "break")[-1])
        reload_list()
        entry.focus_set()

    def _sync_prompt_builder_fields(self):
        for widget_name, state_name in (
            ("prompt_component_name_entry", "prompt_component_name"),
            ("prompt_component_location_entry", "prompt_component_location"),
        ):
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None and widget.winfo_exists():
                    setattr(self, state_name, widget.get().strip())
            except (AttributeError, self.tk.TclError):
                pass

    def _component_pool_key(self):
        model = getattr(self, "current_model", {}) or {}
        return str(model.get("project_path") or model.get("project_name") or "default")

    def _current_component_pool(self):
        pools = getattr(self, "component_pools", {}) or {}
        return list(pools.get(self._component_pool_key()) or [])

    @staticmethod
    def _component_phrase(item):
        surface = str(item.get("surface") or item.get("platform") or "").lower()
        surface_label = {"web": "Web端", "android": "Android端", "windows": "Windows端"}.get(
            surface, str(item.get("platform") or "").strip()
        )
        values = [
            surface_label,
            str(item.get("page") or "").lstrip("📱🌐🪟📡✨ ").strip(),
            str(item.get("area") or item.get("location") or "").strip(),
            str(item.get("name") or "").strip(),
        ]
        parts = []
        for value in values:
            value = re.sub(r"^\[[^\]]+\]\s*", "", value)
            for part in re.split(r"\s*/\s*|\s*·\s*", value):
                part = part.strip()
                if part and part not in parts:
                    parts.append(part)
        return "-".join(parts)

    def _add_component_target(self, item):
        target = dict(item or {})
        phrase = self._component_phrase(target)
        if not phrase:
            return
        key = self._component_pool_key()
        if not hasattr(self, "component_pools"):
            self.component_pools = {}
        pool = self._current_component_pool()
        identity = str(target.get("id") or phrase)
        pool = [
            existing for existing in pool
            if str(existing.get("id") or self._component_phrase(existing)) != identity
        ]
        pool.insert(0, target)
        self.component_pools[key] = pool[:12]
        self._save_input_draft()

    def remove_component_target(self, item):
        key = self._component_pool_key()
        if not hasattr(self, "component_pools"):
            self.component_pools = {}
        identity = str(item.get("id") or self._component_phrase(item))
        self.component_pools[key] = [
            existing for existing in self._current_component_pool()
            if str(existing.get("id") or self._component_phrase(existing)) != identity
        ]
        self._save_input_draft()
        self._render(self.current_model)

    def show_component_pool_menu(self):
        menu = self.tk.Menu(self.root, tearoff=False)
        for item in self._current_component_pool():
            menu.add_command(
                label=self._component_phrase(item)[:80],
                command=lambda value=item: self.insert_component_target(value),
            )
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def insert_component_target(self, item):
        phrase = self._component_phrase(item)
        if not phrase:
            return
        self.prompt_component_name = str(item.get("name") or "").strip()
        self.prompt_component_location = str(
            item.get("location") or item.get("area") or item.get("page") or ""
        ).strip()
        self.prompt_component_ref = {
            key: value for key, value in dict(item).items()
            if key not in {"name", "location"}
        }
        current = self._input_text()
        if phrase not in current:
            self._set_input_text(f"{phrase}{current}" if current else phrase)
        self.input_box.focus_set()
        self.input_box.mark_set("insert", "end-1c")
        self._schedule_input_draft_save()

    def handle_prompt_action(self):
        text = self._input_text()
        if not text:
            self._set_status("请先输入任务内容", "#b42318", 1800)
            return
        if getattr(self, "prompt_component_name", ""):
            self.compose_smart_prompt()
            return

        def suggested(result):
            candidates = result.get("candidates") or []
            if not candidates:
                self._set_status("项目地图中没有匹配的组件，可手动添加目标", "#b42318", 2200)
                return
            menu = self.tk.Menu(self.root, tearoff=False)
            for item in candidates[:5]:
                label = self._component_phrase(item)
                menu.add_command(
                    label=label[:72],
                    command=lambda value=item: (
                        self._add_component_target(value),
                        self.insert_component_target(value),
                        self._render(self.current_model),
                    ),
                )
            menu.add_separator()
            menu.add_command(label="直接优化当前表达", command=self.compose_smart_prompt)
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

        self._run_api(
            "/api/project-map/suggest-components",
            method="POST",
            payload={"text": text, "limit": 5},
            on_success=suggested,
            busy_text="正在从项目地图匹配目标…",
        )

    def compose_smart_prompt(self):
        self._sync_prompt_builder_fields()
        text = self._input_text()
        if not text:
            self._set_status("请先输入需求描述", "#b42318", 1800)
            return

        def composed(result):
            candidates = result.get("candidates") or []
            self.prompt_candidates = [
                candidate for candidate in candidates
                if str(candidate.get("prompt") or "").strip()
            ][:3]
            recognized_name = str(result.get("component_name") or "").strip()
            recognized_location = str(result.get("component_location") or "").strip()
            if recognized_name and recognized_name != "所选组件":
                self.prompt_component_name = recognized_name
            if recognized_location:
                self.prompt_component_location = recognized_location
            prompt = result.get("prompt")
            if not prompt:
                self._set_status("未生成可用提示词", "#b42318")
                return
            self._set_input_text(prompt)
            self._schedule_input_draft_save()
            self._render(self.current_model)
            self._set_status(
                f"已生成 {len(self.prompt_candidates) or 1} 个候选，可在创建页切换",
                "#239957",
                2200,
            )

        capabilities = getattr(self, "current_model", {}).get("capabilities") or []
        active_surface = self._active_tool_surface(capabilities)
        platform_label = next(
            (label for key, _icon, _color, label in PLATFORM_SPECS if key == active_surface),
            "Desktop",
        )
        category = getattr(self, "prompt_task_type", "unspecified")
        self._run_api(
            "/api/prompt/compose",
            method="POST",
            payload={
                "user_text": text,
                "task_type": PROMPT_CATEGORY_TO_COMPOSE_TYPE.get(category, "auto"),
                "category": category,
                "component": {
                    "platform": platform_label,
                    "name": getattr(self, "prompt_component_name", "") or "所选组件",
                    "location": getattr(self, "prompt_component_location", ""),
                    **dict(getattr(self, "prompt_component_ref", {}) or {}),
                },
            },
            on_success=composed,
            busy_text="正在生成智能提示词…",
        )

    def compose_task_smart_prompt(self, task):
        self.active_tab = "create"
        self._set_input_text(task.get("text") or task.get("title") or "")
        self.input_box.focus_set()
        self.compose_smart_prompt()

    def _task_text_with_component(self, text):
        component = str(getattr(self, "prompt_component_name", "") or "").strip()
        location = str(getattr(self, "prompt_component_location", "") or "").strip()
        if not component and not location:
            return text
        if re.search(r"(?m)^(?:定位|组件/类/函数|【界面定位】)\s*[：:]", text):
            return text
        capabilities = getattr(self, "current_model", {}).get("capabilities") or []
        active_surface = self._active_tool_surface(capabilities)
        platform_label = next(
            (label for key, _icon, _color, label in PLATFORM_SPECS if key == active_surface),
            "",
        )
        context = " · ".join(
            part for part in (platform_label, location, component) if part
        )
        return f"目标：{text}\n定位：{context}"

    def create_task(self):
        self._sync_prompt_builder_fields()
        original_text = self._input_text()
        if not original_text:
            self._set_status("请先输入任务内容", "#b42318", 1800)
            return
        text = original_text
        if getattr(self, "test_feedback_task_id", None):
            feedback = text
            if TEST_FEEDBACK_MARKER in feedback:
                feedback = feedback.rsplit(TEST_FEEDBACK_MARKER, 1)[1]
            feedback = feedback.strip()
            if not feedback:
                self._set_status("请在“测试反馈”后输入测试结果", "#b42318", 1800)
                return
            task_id = self.test_feedback_task_id

            def feedback_saved(_result):
                draft = self.input_draft_before_test_feedback
                self.test_feedback_task_id = None
                self.input_draft_before_test_feedback = ""
                self.test_feedback_context = ""
                self._set_input_text(draft)
                self._set_status("测试反馈已提交", "#239957", 1800)
                self.refresh()

            self._run_api(
                "/api/tasks/feedback",
                method="POST",
                payload={"task_id": task_id, "feedback": feedback},
                on_success=feedback_saved,
                busy_text="正在提交测试反馈…",
            )
            return
        if getattr(self, "editing_task_id", None):
            task_id = self.editing_task_id

            def edited(_result):
                draft = self.input_draft_before_task_edit
                self.editing_task_id = None
                self.input_draft_before_task_edit = ""
                self._set_input_text(draft)
                self._set_status("任务已更新并退回待派发", "#239957", 1800)
                self.refresh()

            self._run_api(
                "/api/tasks/edit",
                method="POST",
                payload={"task_id": task_id, "message": text},
                on_success=edited,
                busy_text="正在保存任务…",
            )
            return
        text = self._task_text_with_component(original_text)
        # 创建任务只进入“待派发”；当前选中的 IDE 仅用于下一步点击派发时
        # 作为默认目标，不能在创建阶段把任务写成 queued/进行中。
        payload = {
            "text": text,
            "original_text": original_text,
            "target_ide": "auto",
            "auto_dispatch": False,
            "source": "floating_window",
        }
        current_model = getattr(self, "current_model", {}) or {}
        selected_surface = getattr(self, "selected_surface", None)
        if len(_project_platforms(current_model.get("capabilities"))) > 1 and selected_surface:
            payload["surface"] = selected_surface
        prompt_type = getattr(self, "prompt_task_type", "unspecified")
        classification_type = PROMPT_CATEGORY_TO_CLASSIFICATION_TYPE.get(
            prompt_type, ""
        )
        classification = {
            "surface": selected_surface or self._active_tool_surface(
                current_model.get("capabilities") or []
            ) or "general",
            "task_type": classification_type,
            "ui_location": getattr(self, "prompt_component_location", ""),
            "functional_areas": [],
            "state": "confirmed" if classification_type else "unclassified",
            "source": "user",
        }
        payload["classification"] = classification
        component_ref = dict(getattr(self, "prompt_component_ref", {}) or {})
        component_name = str(getattr(self, "prompt_component_name", "") or "")
        component_location = str(getattr(self, "prompt_component_location", "") or "")
        if component_name or component_location or component_ref:
            payload["component"] = {
                **component_ref,
                "name": component_name,
                "location": component_location,
            }
        if classification_type:
            payload["task_type"] = classification_type
            # classification.task_type 保持后端通用枚举；task_category 保留
            # “功能优化/界面优化”的用户原始选择，供派发前缀准确展示。
            payload["task_category"] = prompt_type

        def created(result):
            task_id = result.get("task_id") or ""
            optimistic_task = {
                "title": text[:60] or "无标题任务",
                "text": text,
                "task_id": task_id,
                "status": "待派发",
                "target_ide": "未分配",
                "surface": _task_surface(
                    {"title": text, "text": text, "metadata": {"surface": selected_surface}},
                    current_model.get("capabilities") or ["general"],
                ),
                "progress": 0,
                "allowed_actions": ["view", "edit", "delete"],
                "feedbacks": [],
                "summary": "",
                "error": "",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "content_kind": "task",
            }
            if self.current_model:
                optimistic_model = {
                    **self.current_model,
                    "tasks": [
                        optimistic_task,
                        *[
                            task for task in self.current_model.get("tasks", [])
                            if not task_id or task.get("task_id") != task_id
                        ],
                    ],
                }
                self._render(optimistic_model)
            self._set_input_text("")
            self.prompt_candidates = []
            self.prompt_component_name = ""
            self.prompt_component_location = ""
            self.prompt_component_ref = {}
            self._set_status("任务已创建", "#239957", 1800)
            self.refresh()

        self._run_api("/api/tasks/create", method="POST", payload=payload, on_success=created, busy_text="正在创建任务…")

    def copy_task(self, task):
        content = task_copy_text(task)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update_idletasks()
        self._set_status("已复制", "#239957", 1400)

    def view_task(self, task):
        dialog = self.tk.Toplevel(self.root)
        dialog.title(task.get("title") or "任务详情")
        dialog.geometry("560x380")
        dialog.attributes("-topmost", True)
        text = self.tk.Text(dialog, wrap="word", relief="flat", padx=14, pady=14)
        text.pack(fill="both", expand=True)
        details = task_copy_text(task)
        meta = f"\n\n任务 ID：{task.get('task_id') or '无'}\n状态：{task.get('status')}\n目标 IDE：{task.get('target_ide')}"
        if task.get("summary"):
            meta += f"\n结果：{task['summary']}"
        if task.get("error"):
            meta += f"\n错误：{task['error']}"
        feedbacks = task.get("feedbacks") or []
        if feedbacks:
            meta += "\n\n反馈记录：\n" + "\n".join(
                f"- {item.get('text') or item}" if isinstance(item, dict) else f"- {item}"
                for item in feedbacks
            )
        text.insert("1.0", details + meta)
        text.config(state="disabled")

    def show_task_menu(self, event, task):
        labels = {
            "confirm_done": "通过",
            "feedback": "反馈问题",
            "feedback_note": "反馈",
            "retry": "重试",
            "dispatch": "派发",
            "assign": "选择 IDE",
            "edit": "编辑",
            "mark_failed": "标记失败",
            "delete": "删除",
        }
        menu = self.tk.Menu(self.root, tearoff=False)
        for action in task.get("allowed_actions") or []:
            if action in {"view"}:
                continue
            label = labels.get(action)
            if label:
                menu.add_command(label=label, command=lambda value=action, item=task: self.execute_task_action(value, item))
        if menu.index("end") is not None:
            menu.add_separator()
        menu.add_command(label="复制", command=lambda: self.copy_task(task))
        menu.add_command(label="查看", command=lambda: self.view_task(task))
        menu.tk_popup(event.x_root, event.y_root)

    def execute_task_action(self, action, task):
        task_id = task.get("task_id")
        if not task_id:
            self._set_status("任务缺少 ID", "#b42318")
            return
        if action == "edit":
            self.test_feedback_task_id = None
            self.input_draft_before_test_feedback = ""
            self.test_feedback_context = ""
            self.input_draft_before_task_edit = self._input_text()
            self.editing_task_id = task_id
            self.active_tab = "create"
            self._render(self.current_model)
            self._set_input_text(task.get("text") or task.get("title") or "")
            self.input_box.focus_set()
            self._set_status("正在编辑任务，按 Enter 保存", "#0867f2")
            return
        if action == "test_feedback":
            body = _clean_task_text(task.get("text") or task.get("title")) or "无任务正文"
            self.editing_task_id = None
            self.input_draft_before_task_edit = ""
            self.input_draft_before_test_feedback = self._input_text()
            self.test_feedback_task_id = task_id
            self.test_feedback_context = f"原任务上下文：\n{body}{TEST_FEEDBACK_MARKER}"
            self.active_tab = "create"
            self._render(self.current_model)
            self._set_input_text(self.test_feedback_context)
            self.input_box.focus_set()
            self.input_box.mark_set("insert", "end-1c")
            self._set_status("补充测试结果后按 Enter 提交", "#0867f2")
            return
        if action == "send_test_feedback":
            summary = str(task.get("test_summary") or "").strip()
            evidence = str(task.get("test_evidence") or "").strip()
            feedback = "测试未通过"
            if summary:
                feedback += f"：{summary}"
            if evidence:
                feedback += f"\n验证证据：{evidence}"
            self._run_api(
                "/api/tasks/feedback",
                method="POST",
                payload={"task_id": task_id, "feedback": feedback},
                on_success=lambda _result: (
                    self._set_status("测试结果已反馈给开发 IDE", "#239957", 1800),
                    self.refresh(),
                ),
                busy_text="正在反馈给开发 IDE…",
            )
            return
        if action == "dispatch_test":
            if not self.selected_ide_key:
                self._set_status("请先选择用于测试的运行中 IDE", "#b42318")
                return
            self._run_api(
                "/api/tasks/test",
                method="POST",
                payload={
                    "task_id": task_id,
                    "test_ide": self.selected_ide_key,
                },
                on_success=lambda _result: (
                    self._set_status("测试任务已派发", "#239957", 1800),
                    self.refresh(),
                ),
                busy_text="正在派发测试任务…",
            )
            return
        if action in {"feedback", "feedback_note"}:
            from tkinter import simpledialog

            feedback = simpledialog.askstring("任务反馈", "请输入反馈或修改要求：", parent=self.root)
            if not feedback:
                return
            self._run_api(
                "/api/tasks/feedback",
                method="POST",
                payload={"task_id": task_id, "feedback": feedback},
                on_success=lambda _result: (self._set_status("反馈已提交", "#239957", 1800), self.refresh()),
                busy_text="正在提交反馈…",
            )
            return
        if action in {"dispatch", "assign"}:
            if not self.selected_ide_key:
                self._set_status("请先选择运行中的 IDE", "#b42318")
                return
            if action == "assign":
                path = f"/api/tasks/{quote(task_id)}/assign"
                payload = {"target_ide": self.selected_ide_key}
            else:
                path = "/api/tasks/dispatch"
                payload = {"task_ids": [task_id], "target_ide": self.selected_ide_key}
            self._run_api(
                path,
                method="POST",
                payload=payload,
                on_success=lambda _result: (self._set_status("任务已派发", "#239957", 1800), self.refresh()),
                busy_text="正在派发任务…",
            )
            return

        route_map = {
            "pending_test": (
                "/api/tasks/complete",
                "POST",
                {"task_id": task_id, "manual": False, "summary": "等待测试"},
            ),
            "complete": ("/api/tasks/complete", "POST", {"task_id": task_id, "manual": True}),
            "confirm_done": (f"/api/tasks/{quote(task_id)}/confirm", "POST", {}),
            "retry": (f"/api/tasks/{quote(task_id)}/retry", "POST", {}),
            "mark_failed": (f"/api/tasks/{quote(task_id)}/fail", "POST", {"error": "用户从浮窗标记失败"}),
            "delete": (f"/api/tasks/{quote(task_id)}", "DELETE", None),
        }
        route = route_map.get(action)
        if not route:
            self._set_status(f"暂不支持操作：{action}", "#b42318")
            return
        path, method, payload = route
        self._run_api(
            path,
            method=method,
            payload=payload,
            on_success=lambda _result: (self._set_status("任务已更新", "#239957", 1800), self.refresh()),
            busy_text="正在更新任务…",
        )

    def show_launch_menu(self, stopped):
        menu = self.tk.Menu(self.root, tearoff=False)
        for ide in stopped:
            menu.add_command(label=ide["name"], command=lambda item=ide: self.start_ide(item))
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def start_ide(self, ide):
        key = ide.get("key")
        path = "/api/oc-web/start" if key == "oc_web" else f"/ide/{quote(key or '')}/start"
        self._run_api(
            path,
            method="POST",
            payload={},
            on_success=lambda result: (self._set_status(result.get("message") or f"{ide.get('name')} 已启动", "#239957", 2200), self.refresh()),
            busy_text=f"正在启动 {ide.get('name')}…",
        )

    def _open_project_picker(self, event):
        if self.drag_moved:
            self._apply_monitor_layout()
            self._save_window_position()
        else:
            self.load_project_menu()

    def load_project_menu(self):
        def loaded(result):
            projects = result.get("projects") or []
            menu = self.tk.Menu(self.root, tearoff=False)
            current = result.get("current_project") or ""
            for project in projects:
                path = project.get("path") or ""
                marker = "✓ " if os.path.normcase(path) == os.path.normcase(current) else ""
                menu.add_command(
                    label=marker + (project.get("name") or os.path.basename(path) or path),
                    command=lambda value=path: self.select_project(value),
                )
            if projects:
                menu.add_separator()
            menu.add_command(label="项目管理…", command=self.open_project_management)
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
            self._set_status("")

        self._run_api("/api/projects", on_success=loaded, busy_text="正在读取项目…")

    def select_project(self, path):
        self._run_api(
            "/api/projects/select",
            method="POST",
            payload={"path": path},
            on_success=lambda _result: (self._set_status("项目已切换", "#239957", 1600), self.refresh()),
            busy_text="正在切换项目…",
        )

    def _render_error(self, message):
        self.connection_failed = True
        # Force a full redraw after reconnection even when the server data is
        # identical to the last successful response.
        self.last_render_signature = None
        self.root.title(WINDOW_TITLE_FALLBACK)
        self.title_label.config(text=WINDOW_TITLE_FALLBACK)
        self._set_status("AideLink 服务正在启动或重启，正在重新连接…（点击复制详情）", "#657084")
        self.status_detail = message
        self._clear_rows(self.ide_frame)
        self._clear_rows(self.task_frame)
        self.tk.Label(self.ide_frame, text="等待服务连接", bg="#ffffff", fg="#8a94a6", anchor="w").pack(fill="x", pady=8)
        self.tk.Label(self.task_frame, text="连接恢复后将自动显示任务", bg="#ffffff", fg="#8a94a6", anchor="w").pack(fill="x", pady=8)

    def _clear_input_hint(self, _event):
        if self.input_box.get("1.0", "end-1c") == INPUT_HINT:
            self.input_box.delete("1.0", "end")
            self.input_box.config(fg="#172033")

    def _update_counter(self, _event=None):
        return None

    def refresh_once(self):
        try:
            payload = fetch_bootstrap()
            return RefreshResult(True, build_home_model(payload))
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return RefreshResult(False, build_home_model({}), f"AideLink 服务连接失败：{exc}")

    def refresh(self):
        if self.refresh_in_progress:
            return
        self.refresh_in_progress = True

        def worker():
            result = self.refresh_once()

            def apply_result():
                self.refresh_in_progress = False
                self._apply_refresh_result(result)

            self._post_ui(apply_result)

        threading.Thread(
            target=worker,
            daemon=True,
            name="AideLinkFloatingWindowRefresh",
        ).start()

    def _apply_refresh_result(self, result):
        if result.ok:
            signature = json.dumps(result.model, ensure_ascii=False, sort_keys=True, default=str)
            if self.connection_failed or signature != self.last_render_signature:
                self.connection_failed = False
                self.last_render_signature = signature
                self._render(result.model)
            if hasattr(self, "root") and not getattr(self, "_startup_quota_done", False):
                self._startup_quota_done = True
                self._maybe_fetch_quota_on_startup()
        else:
            self._render_error(result.error or "AideLink 服务连接失败")

    def _schedule_refresh(self):
        self.root.after(int(self.refresh_seconds * 1000), self._refresh_timer)

    def _refresh_timer(self):
        self.refresh()
        self._schedule_refresh()

    def _start_drag(self, event):
        self.drag_moved = False
        self.drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event):
        self.drag_moved = True
        x = event.x_root - self.drag_start[0]
        y = event.y_root - self.drag_start[1]
        self.root.geometry(f"+{x}+{y}")

    def _finish_drag(self, _event=None):
        if self.drag_moved:
            self._apply_monitor_layout()
            self._save_window_position()

    @staticmethod
    def _virtual_screen_bounds(root):
        if os.name == "nt":
            user32 = ctypes.windll.user32
            return (
                user32.GetSystemMetrics(76),
                user32.GetSystemMetrics(77),
                user32.GetSystemMetrics(78),
                user32.GetSystemMetrics(79),
            )
        return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())

    def _initial_window_position(self, window_height):
        left, top, screen_width, screen_height = self._virtual_screen_bounds(self.root)
        default_x = left + screen_width - self.window_width - 6
        default_y = top + 24
        try:
            state = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            x, y = int(state["x"]), int(state["y"])
        except (OSError, KeyError, TypeError, ValueError):
            x, y = default_x, default_y
        monitor = self._monitor_work_area_at(x + self.window_width // 2, y + 20)
        self._set_monitor_profile(monitor)
        monitor_left, monitor_top, monitor_width, monitor_height = monitor
        max_x = monitor_left + max(0, monitor_width - self.window_width)
        max_y = monitor_top + max(0, monitor_height - min(window_height, monitor_height))
        return max(monitor_left, min(x, max_x)), max(monitor_top, min(y, max_y))

    def _monitor_work_area_at(self, x, y):
        if os.name != "nt":
            return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        point = wintypes.POINT(int(x), int(y))
        monitor = ctypes.windll.user32.MonitorFromPoint(point, 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if monitor and ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcWork
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        return self._virtual_screen_bounds(self.root)

    def _set_monitor_profile(self, monitor):
        _left, _top, width, height = monitor
        if width >= 2400 or height >= 1350:
            self.window_width = 480
            self.min_window_height = 760
            self.max_window_height = min(1040, max(760, height - 40))
        elif width >= 1800 and height >= 1000:
            self.window_width = 440
            self.min_window_height = 680
            self.max_window_height = min(900, max(680, height - 40))
        else:
            self.window_width = WINDOW_WIDTH
            self.min_window_height = 500
            self.max_window_height = min(720, max(500, height - 32))

    def _apply_monitor_layout(self):
        monitor = self._monitor_work_area_at(
            self.root.winfo_x() + self.root.winfo_width() // 2,
            self.root.winfo_y() + 20,
        )
        previous = (self.window_width, self.min_window_height, self.max_window_height)
        self._set_monitor_profile(monitor)
        changed = previous != (self.window_width, self.min_window_height, self.max_window_height)
        self.root.minsize(min(350, self.window_width), self.min_window_height)
        if changed and self.current_model:
            self._render(self.current_model)
        else:
            self._ensure_window_visible(self.root.winfo_height())
        return changed

    def _save_window_position(self):
        self._update_window_state(
            x=self.root.winfo_x(),
            y=self.root.winfo_y(),
        )

    @staticmethod
    def _read_window_state():
        try:
            state = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _update_window_state(cls, **fields):
        try:
            state = cls._read_window_state()
            state.update(fields)
            WINDOW_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = WINDOW_STATE_FILE.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, WINDOW_STATE_FILE)
        except Exception:
            pass

    def _schedule_input_draft_save(self):
        if self.input_draft_after_id is not None:
            self.root.after_cancel(self.input_draft_after_id)
        self.input_draft_after_id = self.root.after(150, self._save_input_draft)

    def _save_input_draft(self):
        self.input_draft_after_id = None
        if not hasattr(self, "input_box"):
            return
        self._update_window_state(
            input_draft=self._input_text(),
            active_tab=getattr(self, "active_tab", "create"),
            prompt_task_type=getattr(self, "prompt_task_type", "unspecified"),
            prompt_component_name=getattr(self, "prompt_component_name", ""),
            prompt_component_location=getattr(self, "prompt_component_location", ""),
            prompt_component_ref=getattr(self, "prompt_component_ref", {}),
            component_pools=getattr(self, "component_pools", {}),
        )

    def _restore_input_draft(self):
        state = self._read_window_state()
        draft = str(state.get("input_draft") or "")
        restored_tab = str(state.get("active_tab") or "")
        if restored_tab in {"create", "manage", "tools"}:
            self.active_tab = restored_tab
        restored_type = str(state.get("prompt_task_type") or "")
        if restored_type in {key for key, _label in PROMPT_TASK_TYPES}:
            self.prompt_task_type = restored_type
        self.prompt_component_name = str(state.get("prompt_component_name") or "").strip()
        self.prompt_component_location = str(
            state.get("prompt_component_location") or ""
        ).strip()
        self.prompt_component_ref = dict(state.get("prompt_component_ref") or {})
        self.component_pools = dict(state.get("component_pools") or {})
        if draft:
            self._set_input_text(draft)
            self.input_box.mark_set("insert", "end-1c")

    def _ensure_window_visible(self, window_height):
        left, top, screen_width, screen_height = self._monitor_work_area_at(
            self.root.winfo_x() + self.root.winfo_width() // 2,
            self.root.winfo_y() + 20,
        )
        x = max(left, min(self.root.winfo_x(), left + max(0, screen_width - self.window_width)))
        y = max(top, min(self.root.winfo_y(), top + max(0, screen_height - window_height)))
        if (x, y) != (self.root.winfo_x(), self.root.winfo_y()):
            self.root.geometry(f"+{x}+{y}")

    def toggle_topmost(self):
        self.is_topmost = not self.is_topmost
        self.root.attributes("-topmost", self.is_topmost)
        self.top_btn.config(image=self.icons.get("pin", 18, "#0867f2" if self.is_topmost else "#657084"))

    def close(self):
        self._save_input_draft()
        self._save_window_position()
        self.root.destroy()

    def activate(self):
        self.root.deiconify()
        self.root.lift()
        if self.is_topmost:
            self.root.attributes("-topmost", True)

    def activate_focus(self):
        """置顶浮窗并把键盘焦点收到输入框。

        派发成功后由 dispatch_task 延迟触发（经信号服务 activate_focus 命令）。
        目的：让目标 IDE 失去前台（但仍可见、不最小化）→ IDE 完成时弹 Windows toast
        （被 watcher 捕获→pending_test），同时 App 端 HWND 截图监控不受影响。
        focus_force 在别的进程占前台时可能失败，故用 Win32 SetForegroundWindow +
        AttachThreadInput 兜底（实测有效）。
        """
        self.activate()
        try:
            self.input_box.focus_set()
            self.root.focus_force()
        except Exception:
            pass
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = self.root.winfo_id()
            # overrideredirect 窗口 winfo_id 通常即顶层 HWND；取祖先兜底
            try:
                root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT=2
                if root_hwnd:
                    hwnd = root_hwnd
            except Exception:
                pass
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
            # 抢到前台后再聚焦输入框，确保键盘输入落到输入框
            self.root.after(60, lambda: self._safe_focus_input())
        except Exception:
            pass

    def _safe_focus_input(self):
        try:
            self.input_box.focus_set()
        except Exception:
            pass

    def _start_signal_server(self):
        def _serve():
            server = None
            try:
                # The previous process may release the loopback port slightly
                # after its window disappears. Retry so the fresh process never
                # loses tray control permanently.
                for _attempt in range(30):
                    candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        candidate.bind(("127.0.0.1", SHOW_SIGNAL_PORT))
                        server = candidate
                        break
                    except OSError:
                        candidate.close()
                        time.sleep(0.1)
                if server is None:
                    return
                server.listen(2)
                while True:
                    conn, _addr = server.accept()
                    with conn:
                        data = conn.recv(32)
                        command = data.strip()
                        if command == b"close":
                            self._post_ui(self.close)
                            return
                        if command == b"activate":
                            self._post_ui(self.activate)
                        if command == b"activate_focus":
                            self._post_ui(self.activate_focus)
            except OSError:
                return
            finally:
                if server is not None:
                    try:
                        server.close()
                    except Exception:
                        pass

        threading.Thread(target=_serve, daemon=True, name="AideLinkFloatingWindowSignal").start()

    def open_settings(self):
        webbrowser.open(f"{BRIDGE_URL.rstrip('/')}/settings.html")

    def open_project_management(self):
        webbrowser.open(f"{BRIDGE_URL.rstrip('/')}/?page=tasks")

    def run(self):
        self.root.mainloop()


def open_floating_window():
    script = Path(__file__).resolve()
    subprocess.Popen(
        [str(Path(sys.executable)), str(script)],
        cwd=str(script.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def send_window_signal(command="activate", timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", SHOW_SIGNAL_PORT), timeout=timeout) as client:
            client.sendall(command.encode("ascii"))
        return True
    except OSError:
        return False


def close_floating_window(timeout=0.5):
    return send_window_signal("close", timeout=timeout)


def main():
    instance = SingleInstance()
    if not instance.acquire():
        send_window_signal("activate")
        return 0
    try:
        app = FloatingWindowApp()
        app.run()
        return 0
    finally:
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
