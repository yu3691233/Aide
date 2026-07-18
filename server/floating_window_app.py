import ctypes
import json
import os
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


BRIDGE_URL = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000")
BOOTSTRAP_URL = f"{BRIDGE_URL.rstrip('/')}/api/floating-window/bootstrap"
WINDOW_MUTEX_NAME = "Local\\AideLinkFloatingWindow"
WINDOW_TITLE_FALLBACK = "暂无项目"
SHOW_SIGNAL_PORT = int(os.environ.get("AIDELINK_FLOATING_WINDOW_PORT", "51231"))
VISIBLE_TASK_ACTIONS = ("copy", "view", "more")


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
    return ("📱" if "android" in capabilities else "") + ("🌐" if "web" in capabilities else "")


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
        "draft": "未派发",
        "failed": "失败",
        "timeout": "超时",
        "done": "已完成",
    }.get(status or "", status or "未知")


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

    needs_user = int(summary.get("needs_user") or 0)
    by_status = summary.get("by_status") or {}
    pending_test = int(by_status.get("pending_test") or 0)
    running = int(by_status.get("running") or 0) + int(by_status.get("dispatched") or 0) + int(by_status.get("queued") or 0)

    capabilities = payload.get("capabilities") or project.get("capabilities") or ["general"]
    project_name = _project_name(project)
    badge = _capability_badge(capabilities)

    return {
        "title": f"{project_name} {badge}".strip(),
        "project_name": _project_name(project),
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
            }
            for ide in ides
        ],
        "selected_target": selected.get("name") or selected.get("key") or "未选择 IDE",
        "selected_target_key": selected.get("key"),
        "summary": {
            "待处理": needs_user,
            "待测试": pending_test,
            "进行中": running,
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
            }
            for task in tasks[:5]
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
        self.current_model = {}
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE_FALLBACK)
        self.root.geometry("660x620+850+70")
        self.root.minsize(580, 520)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.transparent_color = "#ff00ff"
        self.root.configure(bg=self.transparent_color)
        if os.name == "nt":
            self.root.attributes("-transparentcolor", self.transparent_color)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(0, self._enable_rounded_window)
        self._build_ui()
        self.refresh()
        self._start_signal_server()
        self._schedule_refresh()

    def _build_ui(self):
        tk = self.tk
        bg = "#f8fafc"
        card = "#ffffff"
        border = "#dbe2ea"
        text = "#172033"
        muted = "#657084"
        blue = "#0867f2"

        outer = tk.Canvas(self.root, bg=self.transparent_color, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        shell = tk.Frame(outer, bg=bg)
        shell_window = outer.create_window(8, 8, anchor="nw", window=shell)
        def _resize_shell(event):
            outer.delete("outer-shape")
            self._draw_round_rect(outer, 1, 1, event.width - 1, event.height - 1, 30, fill=bg, outline="#cfd7e3", width=1, tags="outer-shape")
            outer.tag_lower("outer-shape")
            outer.itemconfigure(shell_window, width=max(1, event.width - 16), height=max(1, event.height - 16))
        outer.bind("<Configure>", _resize_shell)

        self.title_bar = tk.Frame(shell, bg=card, height=54, highlightthickness=0)
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)
        self.title_bar.bind("<ButtonPress-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._drag)

        project_box = tk.Frame(self.title_bar, bg=card, highlightthickness=0)
        project_box.pack(side="left", padx=14, pady=7)
        self.title_label = tk.Label(project_box, text=WINDOW_TITLE_FALLBACK, fg=text, bg=card, font=("Microsoft YaHei UI", 12, "bold"), anchor="w", padx=12)
        self.title_label.pack(side="left", ipady=7)
        self.title_label.bind("<ButtonPress-1>", self._start_drag)
        self.title_label.bind("<B1-Motion>", self._drag)
        self.title_label.bind("<ButtonRelease-1>", self._open_project_picker)
        tk.Label(project_box, text="⌄", fg=text, bg=card, font=("Segoe UI Symbol", 13)).pack(side="left", padx=(0, 10))
        tk.Frame(project_box, bg=border, width=1, height=28).pack(side="left", padx=2)
        self.capability_label = tk.Label(project_box, text="📱  🌐", fg=blue, bg=card, font=("Segoe UI Emoji", 13), padx=10)
        self.capability_label.pack(side="left")

        actions = tk.Frame(self.title_bar, bg=card, highlightthickness=0)
        actions.pack(side="right", padx=14, pady=7)
        self.top_btn = self._flat_button(actions, "⌖  置顶", self.toggle_topmost)
        self.top_btn.pack(side="left", padx=1)
        self.close_btn = self._flat_button(actions, "✕  关闭", self.close)
        self.close_btn.pack(side="left", padx=1)
        self.settings_btn = self._flat_button(actions, "⚙  设置", self.open_settings)
        self.settings_btn.pack(side="left", padx=1)

        self.input_frame = tk.Frame(shell, bg=bg)
        self.input_frame.pack(side="bottom", fill="x", padx=14, pady=(4, 10))

        input_shell = tk.Canvas(self.input_frame, bg=bg, height=70, highlightthickness=0)
        input_shell.pack(fill="x")
        self.input_box = tk.Text(input_shell, height=2, wrap="word", relief="flat", bd=0, bg=card, fg=text, insertbackground=text, font=("Microsoft YaHei UI", 10))
        input_window = input_shell.create_window(12, 8, anchor="nw", window=self.input_box)
        self.input_box.insert("1.0", "输入要发送的内容，修改要求或想法…")
        self.input_box.config(fg="#8a94a6")
        self.input_box.bind("<FocusIn>", self._clear_input_hint)
        self.counter_label = tk.Label(input_shell, text="0/2000   ↗", bg=card, fg=muted)
        counter_window = input_shell.create_window(620, 56, anchor="e", window=self.counter_label)
        def _resize_input(event):
            input_shell.delete("rounded-bg")
            self._draw_round_rect(input_shell, 1, 1, event.width - 1, 69, 14, fill=card, outline="#aeb8c6", tags="rounded-bg")
            input_shell.tag_lower("rounded-bg")
            input_shell.itemconfigure(input_window, width=max(100, event.width - 24), height=38)
            input_shell.coords(counter_window, event.width - 10, 56)
        input_shell.bind("<Configure>", _resize_input)
        self.input_box.bind("<KeyRelease>", self._update_counter)

        bottom_actions = tk.Frame(self.input_frame, bg=bg)
        bottom_actions.pack(fill="x", pady=(10, 0))
        self.send_btn = self._rounded_button(bottom_actions, "✈  暂无可用 IDE", self._send_input, width=145, height=40, fill=blue, outline=blue, fg="#ffffff", bold=True)
        self.send_btn.pack(side="left")
        actions_map = (
            ("快捷回复", "💬", self.show_quick_reply_menu),
            ("智能提示词", "✦", self.compose_smart_prompt),
            ("创建任务", "＋", self.create_task),
            ("保存随记", "▱", self.save_inspiration),
        )
        for label, icon, command in actions_map:
            short = {"创建任务": "创建", "保存随记": "随记"}.get(label, label)
            self._rounded_button(bottom_actions, f"{icon} {short}", command, width=105, height=40, fill="#ffffff", outline=border, fg="#283246").pack(side="left", padx=(5, 0))

        body = tk.Frame(shell, bg=bg)
        body.pack(fill="both", expand=True)

        ide_section = tk.Frame(body, bg=card)
        ide_section.pack(fill="x", padx=14, pady=8)
        self.ide_frame = tk.Frame(ide_section, bg=card)
        self.ide_frame.pack(fill="x")

        separator = tk.Frame(body, bg=border, height=1)
        separator.pack(fill="x", pady=4)
        task_section = tk.Frame(body, bg=bg)
        task_section.pack(fill="both", expand=True, padx=14, pady=(7, 0))
        self.summary_frame = tk.Frame(task_section, bg=bg)
        self.summary_frame.pack(fill="x", pady=(5, 5))
        self.task_frame = tk.Frame(task_section, bg=bg)
        self.task_frame.pack(fill="both", expand=True)
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

    @staticmethod
    def _draw_round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _rounded_button(self, parent, text, command, width, height, fill, outline, fg, bold=False):
        canvas = self.tk.Canvas(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, cursor="hand2")
        canvas._shape_item = self._draw_round_rect(canvas, 1, 1, width - 1, height - 1, 16, fill=fill, outline=outline, width=1)
        canvas._command = command
        font = ("Microsoft YaHei UI", 10, "bold" if bold else "normal")
        canvas._text_item = canvas.create_text(width / 2, height / 2, text=text, fill=fg, font=font)
        canvas.bind("<Button-1>", lambda _event: command())
        return canvas

    def _clear_rows(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _render(self, model):
        tk = self.tk
        self.current_model = model
        self.selected_ide_key = choose_selected_ide(
            self.selected_ide_key,
            model["ides"],
            model.get("selected_target_key"),
        )
        self.root.title(model["title"])
        compact_height = max(520, min(650, 360 + len(model["tasks"][:5]) * 62))
        self.root.geometry(f"660x{compact_height}")
        self.title_label.config(text=model["project_name"])
        self.capability_label.config(text="  ".join(filter(None, (
            "🤖" if "android" in model["capabilities"] else "",
            "🌐" if "web" in model["capabilities"] else "",
        ))) or "◌")
        self.status_label.config(text="", fg="#3a4150")

        self._clear_rows(self.ide_frame)
        running = [ide for ide in model["ides"] if ide["running"]]
        stopped = [ide for ide in model["ides"] if not ide["running"]]
        if running:
            for ide in running:
                selected = ide["key"] == self.selected_ide_key
                dot = "#13b96d" if not ide["busy"] else "#f5a900"
                button = self._rounded_button(
                    self.ide_frame,
                    f"●   {ide['name']}",
                    lambda key=ide["key"]: self.select_ide(key),
                    width=125,
                    height=42,
                    fill="#f7fbff" if selected else "#ffffff",
                    outline="#0867f2" if selected else "#dbe2ea",
                    fg="#0867f2" if selected else dot,
                    bold=selected,
                )
                button.pack(side="left", padx=(0, 14))
        else:
            tk.Label(self.ide_frame, text="暂无运行中的 IDE", bg="#ffffff", fg="#777f8f", anchor="w").pack(side="left", fill="x", expand=True, pady=10)
        if stopped:
            self._rounded_button(
                self.ide_frame, "＋ 启动 IDE", lambda: self.show_launch_menu(stopped),
                width=78, height=42, fill="#ffffff", outline="#ffffff", fg="#0867f2",
            ).pack(side="right")

        self._clear_rows(self.summary_frame)
        summary_styles = {
            "待处理": ("#fff6f6", "#ef3f45", "#f6c9cc"),
            "待测试": ("#fff9ef", "#f08a00", "#f5d8ae"),
            "进行中": ("#f3f8ff", "#0867f2", "#c9dcfb"),
        }
        for key, value in model["summary"].items():
            bg, fg, border = summary_styles[key]
            icon = {"待处理": "ⓘ", "待测试": "◷", "进行中": "⟳"}[key]
            self._rounded_button(
                self.summary_frame, f"{icon}  {key}   {value}", lambda: None,
                width=170, height=44, fill=bg, outline=border, fg=fg,
            ).pack(side="left", padx=(0, 8))

        self._clear_rows(self.task_frame)
        if model["tasks"]:
            list_card = tk.Canvas(self.task_frame, bg="#f8fafc", highlightthickness=0)
            list_card.pack(fill="both", expand=True)
            tasks = model["tasks"][:5]
            row_height = 62
            total_height = max(64, row_height * len(tasks) + 4)
            list_card.config(scrollregion=(0, 0, 600, total_height))
            list_card.bind("<MouseWheel>", lambda event: list_card.yview_scroll(int(-event.delta / 120), "units"))
            self._draw_round_rect(list_card, 1, 1, 600, total_height - 1, 16, fill="#ffffff", outline="#dbe2ea")
            type_labels = {
                "android": ("Android", "#effaf3", "#24864b"),
                "web": ("Web", "#eff6ff", "#0867f2"),
                "general": ("通用", "#f4f1ff", "#7657d9"),
            }
            for index, task in enumerate(tasks):
                y = 2 + index * row_height
                if index:
                    list_card.create_line(1, y, 600, y, fill="#edf0f4")
                status_color = {"待测试": "#f08a00", "执行中": "#0867f2", "待修复": "#ef3f45", "超时": "#ef3f45"}.get(task["status"], "#ef3f45")
                list_card.create_oval(12, y + 14, 22, y + 24, fill=status_color, outline=status_color)
                title = task["title"] if len(task["title"]) <= 24 else task["title"][:23] + "…"
                list_card.create_text(32, y + 19, text=title, fill="#20293a", anchor="w", font=("Microsoft YaHei UI", 9, "bold"))

                type_name, type_bg, type_fg = type_labels.get(task["surface"], type_labels["general"])
                self._draw_round_rect(list_card, 32, y + 35, 78, y + 55, 7, fill=type_bg, outline=type_bg)
                list_card.create_text(55, y + 45, text=type_name, fill=type_fg, font=("Microsoft YaHei UI", 8))
                subtitle = f"{task['target_ide']}  ·  {task['status']}"
                progress = max(0, min(100, task.get("progress") or 0))
                if task["status"] == "执行中" and progress:
                    subtitle += f"  ·  {progress}%"
                list_card.create_text(86, y + 45, text=subtitle, fill="#657084", anchor="w", font=("Microsoft YaHei UI", 8))

                actions = (("复制", 430, 474), ("查看", 480, 524), ("···", 530, 578))
                for action, x1, x2 in actions:
                    tag = f"{action}-{index}"
                    self._draw_round_rect(list_card, x1, y + 14, x2, y + 45, 8, fill="#ffffff", outline="#dbe2ea", tags=tag)
                    list_card.create_text((x1 + x2) / 2, y + 30, text=action, fill="#283246", font=("Microsoft YaHei UI", 8), tags=tag)
                    if action == "复制":
                        callback = lambda _event, item=task: self.copy_task(item)
                    elif action == "查看":
                        callback = lambda _event, item=task: self.view_task(item)
                    else:
                        callback = lambda event, item=task: self.show_task_menu(event, item)
                    list_card.tag_bind(tag, "<Button-1>", callback)
        else:
            tk.Label(self.task_frame, text="当前没有待处理任务", bg="#f8fafc", fg="#777f8f", anchor="w").pack(fill="x", pady=10)

        selected_ide = next((ide for ide in model["ides"] if ide["key"] == self.selected_ide_key), None)
        if selected_ide:
            self.send_btn.itemconfigure(self.send_btn._text_item, text=f"✈  发送到 {selected_ide['name']}", fill="#ffffff")
            self.send_btn.itemconfigure(self.send_btn._shape_item, fill="#0867f2", outline="#0867f2")
            self.send_btn.bind("<Button-1>", lambda _event: self._send_input())
        else:
            self.send_btn.itemconfigure(self.send_btn._text_item, text="暂无可用 IDE", fill="#657084")
            self.send_btn.itemconfigure(self.send_btn._shape_item, fill="#e5e9ef", outline="#d5dbe4")
            self.send_btn.unbind("<Button-1>")

    def select_ide(self, key):
        self.selected_ide_key = key
        self._render(self.current_model)

    def _input_text(self):
        value = self.input_box.get("1.0", "end-1c").strip()
        return "" if value == "输入要发送的内容，修改要求或想法…" else value

    def _set_input_text(self, value):
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", value)
        self.input_box.config(fg="#172033")
        self._update_counter()

    def _set_status(self, message, color="#657084", clear_after=0):
        self.status_label.config(text=message, fg=color)
        if clear_after:
            self.root.after(clear_after, lambda: self.status_label.config(text=""))

    def _run_api(self, path, method="GET", payload=None, on_success=None, busy_text="处理中…"):
        self._set_status(busy_text)

        def worker():
            try:
                result = api_request(path, method=method, payload=payload)
            except Exception as exc:
                message = str(exc)
                self.root.after(0, lambda value=message: self._set_status(f"操作失败：{value}", "#b42318"))
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

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True, name="AideLinkFloatingWindowApi").start()

    def _send_input(self):
        text = self._input_text()
        if not text:
            self._set_status("请输入要发送的内容", "#b42318", 1800)
            return
        if not self.selected_ide_key:
            self._set_status("暂无可用 IDE", "#b42318", 1800)
            return

        def sent(result):
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

    def show_quick_reply_menu(self):
        # Match the App defaults; selecting one only fills the shared input.
        replies = ("继续", "安装到手机", "升级版本号并提交git")
        menu = self.tk.Menu(self.root, tearoff=False)
        for reply in replies:
            menu.add_command(label=reply, command=lambda value=reply: self._set_input_text(value))
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def compose_smart_prompt(self):
        text = self._input_text()
        if not text:
            self._set_status("请先输入需求描述", "#b42318", 1800)
            return

        def composed(result):
            candidates = result.get("candidates") or []
            if candidates:
                menu = self.tk.Menu(self.root, tearoff=False)
                for candidate in candidates:
                    prompt = candidate.get("prompt") or ""
                    if prompt:
                        menu.add_command(
                            label=candidate.get("title") or "提示词候选",
                            command=lambda value=prompt: (
                                self._set_input_text(value),
                                self._set_status("已选择智能提示词", "#239957", 1800),
                            ),
                        )
                if menu.index("end") is not None:
                    self._set_status("请选择提示词候选", "#239957")
                    menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
                    return
            prompt = result.get("prompt")
            if not prompt:
                self._set_status("未生成可用提示词", "#b42318")
                return
            self._set_input_text(prompt)
            self._set_status("已生成智能提示词", "#239957", 1800)

        self._run_api(
            "/api/prompt/compose",
            method="POST",
            payload={
                "user_text": text,
                "task_type": "auto",
                "component": {"platform": "Desktop", "name": "AideLink 浮窗输入"},
            },
            on_success=composed,
            busy_text="正在生成智能提示词…",
        )

    def create_task(self):
        text = self._input_text()
        if not text:
            self._set_status("请先输入任务内容", "#b42318", 1800)
            return
        payload = {
            "text": text,
            "target_ide": self.selected_ide_key or "auto",
            "auto_dispatch": False,
        }

        def created(_result):
            self._set_input_text("")
            self._set_status("任务已创建", "#239957", 1800)
            self.refresh()

        self._run_api("/api/tasks/create", method="POST", payload=payload, on_success=created, busy_text="正在创建任务…")

    def save_inspiration(self):
        text = self._input_text()
        if not text:
            self._set_status("请先输入随记内容", "#b42318", 1800)
            return

        def saved(_result):
            self._set_input_text("")
            self._set_status("随记已保存", "#239957", 1800)

        self._run_api("/api/tasks/inspiration", method="POST", payload={"text": text}, on_success=saved, busy_text="正在保存随记…")

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
            from tkinter import simpledialog

            updated = simpledialog.askstring(
                "编辑任务",
                "修改任务内容：",
                initialvalue=task.get("text") or task.get("title") or "",
                parent=self.root,
            )
            if not updated:
                return
            self._run_api(
                "/api/tasks/edit",
                method="POST",
                payload={"task_id": task_id, "message": updated},
                on_success=lambda _result: (self._set_status("任务已更新", "#239957", 1800), self.refresh()),
                busy_text="正在保存任务…",
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
        if not self.drag_moved:
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
            menu.add_command(label="项目设置…", command=self.open_settings)
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
        self.root.title(WINDOW_TITLE_FALLBACK)
        self.title_label.config(text=WINDOW_TITLE_FALLBACK)
        self.status_label.config(text=message, fg="#b42318")
        self._clear_rows(self.ide_frame)
        self._clear_rows(self.task_frame)
        self.tk.Label(self.ide_frame, text="暂无可用 IDE", bg="#ffffff", fg="#777f8f", anchor="w").pack(fill="x", pady=8)
        self.tk.Label(self.task_frame, text="当前没有待处理任务", bg="#f8fafc", fg="#777f8f", anchor="w").pack(fill="x", pady=8)

    def _clear_input_hint(self, _event):
        if self.input_box.get("1.0", "end-1c") == "输入要发送的内容，修改要求或想法…":
            self.input_box.delete("1.0", "end")
            self.input_box.config(fg="#172033")

    def _update_counter(self, _event=None):
        length = len(self.input_box.get("1.0", "end-1c"))
        self.counter_label.config(text=f"{length}/2000   ↗")

    def refresh_once(self):
        try:
            payload = fetch_bootstrap()
            return RefreshResult(True, build_home_model(payload))
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return RefreshResult(False, build_home_model({}), f"AideLink 服务连接失败：{exc}")

    def refresh(self):
        result = self.refresh_once()
        if result.ok:
            self._render(result.model)
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

    def toggle_topmost(self):
        self.is_topmost = not self.is_topmost
        self.root.attributes("-topmost", self.is_topmost)
        self.top_btn.config(text="置顶" if self.is_topmost else "普通")

    def close(self):
        self.root.destroy()

    def activate(self):
        self.root.deiconify()
        self.root.lift()
        if self.is_topmost:
            self.root.attributes("-topmost", True)

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
                            self.root.after(0, self.close)
                            return
                        if command == b"activate":
                            self.root.after(0, self.activate)
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
