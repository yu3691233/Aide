import tkinter as tk
from paths import ASSETS_DIR, HISTORY_FILE as CHAT_HISTORY
from json_utils import safe_read_json

JSON_PATH = str(CHAT_HISTORY)

CHECK_INTERVAL = 2000
BUBBLE_DURATION = 5000

STATE_FILES = {
    "idle":      "assistant-state-12-idle.png",
    "received":  "assistant-state-01-received.png",
    "thinking":  "assistant-state-08-thinking.png",
    "executing": "assistant-state-07-executing.png",
    "completed": "assistant-state-11-completed.png",
    "trouble":   "assistant-state-09-troubleshoot.png",
    "default":   "assistant-portrait.png",
}


def load_state_image(state: str, size: int = 160):
    from PIL import Image, ImageTk
    name = STATE_FILES.get(state, STATE_FILES["default"])
    candidates = [
        ASSETS_DIR / "working-states" / name,
        ASSETS_DIR / name,
        ASSETS_DIR / "assistant-portrait.png",
    ]
    for p in candidates:
        if p.exists():
            img = Image.open(p).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
    return None


class MascotBase:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AideLink 小助理")
        self.root.overrideredirect(True)

        self.width = 160
        self.height = 160
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - self.width - 60
        y = screen_h - self.height - 80
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)

        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg="white",
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.config(cursor="hand2")

        self.current_state = "idle"
        self.image_ref = None
        self.render_state(self.current_state)

        self.last_text = ""
        self.bubble = None
        self.drag_data = {"x": 0, "y": 0}

        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.on_drag)

    def render_state(self, state: str):
        img = load_state_image(state, self.width)
        self.canvas.delete("all")
        if img is None:
            self.canvas.create_text(
                self.width // 2, self.height // 2,
                text="AideLink", fill="#FB923C",
                font=("Microsoft YaHei", 12, "bold"),
            )
            return
        self.image_ref = img
        self.canvas.create_image(self.width // 2, self.height // 2, image=self.image_ref)

    def set_state(self, state: str):
        if state == self.current_state:
            return
        self.current_state = state
        self.render_state(state)

    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def on_drag(self, event):
        dx = event.x - self.drag_data["x"]
        dy = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def check_updates(self):
        try:
            history = safe_read_json(CHAT_HISTORY, [])
            if isinstance(history, list) and history:
                    last = history[-1]
                    sender = last.get("sender", "")
                    text = last.get("text", "")
                    if sender == "phone" and text != self.last_text:
                        self.set_state("received")
                        self.show_bubble(f"收到: {text[:30]}...")
                    elif sender == "agent":
                        self.set_state("thinking")
                    self.last_text = text
        except Exception:
            pass
        self.root.after(CHECK_INTERVAL, self.check_updates)

    def show_bubble(self, text: str):
        if self.bubble is not None:
            self.canvas.delete(self.bubble)
        self.bubble = self.canvas.create_text(
            self.width // 2, 10,
            text=text, fill="#1F2937",
            font=("Microsoft YaHei", 9),
            width=self.width - 20,
        )
        self.root.after(BUBBLE_DURATION, self.hide_bubble)

    def hide_bubble(self):
        if self.bubble is not None:
            self.canvas.delete(self.bubble)
            self.bubble = None
