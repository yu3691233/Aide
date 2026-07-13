"""
AideLink 小助理 — 桌面浮窗
============================
启动方式：python mascot.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from mascot_core import MascotBase


class Mascot(MascotBase):
    def __init__(self):
        super().__init__()
        self.canvas.bind("<Button-3>", lambda e: self.root.destroy())
        self.canvas.bind("<Double-Button-1>", lambda e: self.root.destroy())
        self.check_updates()
        self.root.mainloop()


if __name__ == "__main__":
    Mascot()
