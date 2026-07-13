"""
AideLink 小助理 — 桌面控制台 + 系统托盘
==========================================
启动方式：python mascot_tray.py
"""
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from mascot_core import MascotBase, ASSETS_DIR
from manager_utils import acquire_tray_single_instance

TRAY_ICON_PATH = ASSETS_DIR / "tray-icon.png"


class MascotTrayApp(MascotBase):
    def __init__(self):
        self.visible = True
        super().__init__()
        self.canvas.bind("<Button-3>", self.hide_window)
        self.canvas.bind("<Double-Button-1>", self.hide_window)
        self.tray_icon = None
        self.start_tray()
        self.check_updates()
        self.root.mainloop()

    def show_window(self):
        self.root.deiconify()
        self.visible = True

    def hide_window(self, *_):
        self.root.withdraw()
        self.visible = False

    def quit_app(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def start_tray(self):
        try:
            import pystray
            from pystray import MenuItem as Item
            from PIL import Image

            if TRAY_ICON_PATH.exists():
                icon_img = Image.open(TRAY_ICON_PATH).convert("RGBA")
            else:
                icon_img = Image.new("RGBA", (64, 64), (251, 146, 60, 255))

            menu = pystray.Menu(
                Item("显示小助理", lambda: self.root.after(0, self.show_window)),
                Item("隐藏小助理", lambda: self.root.after(0, self.hide_window)),
                pystray.Menu.SEPARATOR,
                Item("退出 AideLink", lambda: self.root.after(0, self.quit_app)),
            )
            self.tray_icon = pystray.Icon("AideLink", icon_img, "AideLink 小助理", menu)

            def _run_tray():
                try:
                    self.tray_icon.run()
                except Exception as e:
                    print(f"[tray] pystray error: {e}", file=sys.stderr)

            t = threading.Thread(target=_run_tray, daemon=True)
            t.start()
        except ImportError:
            print("[tray] pystray not installed; tray disabled.", file=sys.stderr)


if __name__ == "__main__":
    if acquire_tray_single_instance():
        MascotTrayApp()
