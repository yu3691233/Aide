import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from PIL import Image, ImageDraw

from prompt_generator import generate_prompt
from project_map_client import fetch_project_map, match_element
from websocket_server import WsServer


def create_tray_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = size // 8
    d.ellipse([margin, margin, size - margin, size - margin], fill="#4A90D9")
    d.text((size // 3, size // 3), "A", fill="white")
    return img


class LocatorApp:
    def __init__(self):
        self.ws_server = WsServer()
        self.ws_server.on_element = self._on_element
        self.project_map: list[dict] = []

        self.root = tk.Tk()
        self.root.title("AideLink 组件定位器")
        self.root.geometry("780x520")
        self.root.withdraw()

        self._build_ui()
        self._setup_tray()
        self._start_ws()

        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)

    def _build_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=6, pady=4)

        tk.Button(top, text="匹配代码", command=self._match_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="生成指令", command=self._generate_prompt).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="清空", command=self._clear_all).pack(side=tk.LEFT, padx=2)

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        left = tk.Frame(paned)
        self.tree = ttk.Treeview(left, columns=("tag", "text", "url"), show="headings", selectmode="browse")
        self.tree.heading("tag", text="标签")
        self.tree.heading("text", text="文本")
        self.tree.heading("url", text="URL")
        self.tree.column("tag", width=60, stretch=False)
        self.tree.column("text", width=220)
        self.tree.column("url", width=200)
        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(left, minsize=300)

        right = tk.Frame(paned)
        self.detail = scrolledtext.ScrolledText(right, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self.detail.pack(fill=tk.BOTH, expand=True)
        paned.add(right, minsize=250)

        self.elements: list[dict] = []
        self.matches: dict[int, dict] = {}
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN).pack(fill=tk.X, side=tk.BOTTOM)

    def _setup_tray(self):
        try:
            import pystray

            icon_img = create_tray_icon()
            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._show_window, default=True),
                pystray.MenuItem("退出", self._quit),
            )
            self.tray = pystray.Icon("AideLink", icon_img, "AideLink 组件定位器", menu)
            self.tray.on_activate = lambda: self.root.after(0, self._toggle_window)

            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:
            self.tray = None

    def _start_ws(self):
        self.ws_server.start()
        self.status_var.set("WebSocket ws://127.0.0.1:9876 已启动")

    def _on_element(self, data: dict):
        self.root.after(0, self._add_element, data)

    def _add_element(self, data: dict):
        self.elements.append(data)
        tag = data.get("tag", "?")
        text = (data.get("text") or "").strip()[:60]
        url = data.get("url", "")
        self.tree.insert("", tk.END, iid=str(len(self.elements) - 1), values=(tag, text, url))
        self.status_var.set(f"已收集 {len(self.elements)} 个组件")

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        data = self.elements[idx]
        match = self.matches.get(idx)
        self._show_detail(data, match)

    def _show_detail(self, data: dict, match: dict | None = None):
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        lines = [
            f"标签:     {data.get('tag', '')}",
            f"ID:       {data.get('id', '')}",
            f"Class:    {data.get('className', '')}",
            f"文本:     {(data.get('text') or '').strip()[:120]}",
            f"aria:     {data.get('ariaLabel', '')}",
            f"XPath:    {data.get('xpath', '')}",
            f"CSS:      {data.get('cssSelector', '')}",
            f"位置:     {data.get('rect', {})}",
            f"URL:      {data.get('url', '')}",
        ]
        if match:
            lines += [
                "",
                "--- 匹配结果 ---",
                f"文件:     {match['file']}",
                f"行号:     {match['line']}",
                f"标签:     {match['label']}",
                f"描述:     {match.get('description', '')}",
            ]
        self.detail.insert(tk.END, "\n".join(lines))
        self.detail.configure(state=tk.DISABLED)

    def _match_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if not self.project_map:
            self.project_map = fetch_project_map()
            self.status_var.set(f"已加载项目地图 ({len(self.project_map)} 条)")
        m = match_element(self.elements[idx], self.project_map)
        if m:
            self.matches[idx] = m
            self._show_detail(self.elements[idx], m)
            self.status_var.set(f"匹配到 {m['file']}:{m['line']}")
        else:
            self.status_var.set("未匹配到项目地图")

    def _generate_prompt(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        el = self.elements[idx]
        prompt = generate_prompt(el, self.matches.get(idx))

        win = tk.Toplevel(self.root)
        win.title("生成指令")
        win.geometry("500x200")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        txt.insert(tk.END, prompt)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)

        tk.Button(win, text="复制到剪贴板", command=copy).pack(pady=4)

    def _clear_all(self):
        self.elements.clear()
        self.matches.clear()
        self.tree.delete(*self.tree.get_children())
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.configure(state=tk.DISABLED)
        self.status_var.set("已清空")

    def _show_window(self, _icon=None, _item=None):
        self.root.after(0, self._do_show)

    def _do_show(self):
        self.root.deiconify()
        self.root.lift()

    def _hide_window(self):
        self.root.withdraw()

    def _toggle_window(self):
        if self.root.state() == "withdrawn":
            self._do_show()
        else:
            self._hide_window()

    def _quit(self, _icon=None, _item=None):
        self.ws_server.stop()
        if self.tray:
            self.tray.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LocatorApp()
    app.run()
