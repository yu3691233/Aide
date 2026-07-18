"""Image-backed icons for the Tk floating window.

Common actions use vendored Lucide assets. IDE targets use the installed
application's own icon when Windows can extract one.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageTk
from ide_icon_cache import cached_ide_icon


ASSET_DIR = Path(__file__).resolve().parent / "brand_assets" / "floating-icons"
ICON_FILES = {
    "pin": "pin.png",
    "minus": "minus.png",
    "x": "x.png",
    "settings": "settings.png",
    "bot": "bot.png",
    "chevron_down": "chevron-down.png",
    "chevron_up": "chevron-up.png",
    "clock": "clock-3.png",
    "loader": "loader-circle.png",
    "alert": "circle-alert.png",
    "copy": "copy.png",
    "dispatch": "square-arrow-out-up-right.png",
    "more": "ellipsis.png",
    "plus": "plus.png",
    "list": "list-todo.png",
    "send": "arrow-up.png",
    "smartphone": "smartphone.png",
    "globe": "globe.png",
    "help": "circle-help.png",
    "wifi": "wifi.png",
    "expand": "maximize-2.png",
}


class IconFactory:
    def __init__(self, master):
        self.master = master
        self._cache = {}

    def get(self, name, size=18, color="#263246"):
        key = ("common", name, size, color)
        if key not in self._cache:
            image = self._load_common(name, size, color)
            self._cache[key] = ImageTk.PhotoImage(image, master=self.master)
        return self._cache[key]

    def ide(self, ide_key, executable_path, size=18):
        key = ("ide", ide_key, executable_path, size)
        if key not in self._cache:
            image = self._load_ide_image(ide_key, executable_path, size)
            self._cache[key] = ImageTk.PhotoImage(image, master=self.master)
        return self._cache[key]

    def ide_badge(self, ide_key, executable_path, selected=False, size=30):
        key = ("ide_badge", ide_key, executable_path, selected, size)
        if key not in self._cache:
            scale = 4
            ring = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
            draw = ImageDraw.Draw(ring)
            inset = 2 * scale
            draw.ellipse(
                (inset, inset, size * scale - inset - 1, size * scale - inset - 1),
                fill="#ffffff",
                outline="#0867f2" if selected else "#d8dee8",
                width=2 * scale,
            )
            badge = ring.resize((size, size), Image.Resampling.LANCZOS)
            icon_size = max(20, int(size * 0.68))
            icon = self._load_ide_image(ide_key, executable_path, icon_size)
            badge.alpha_composite(
                icon,
                ((size - icon.width) // 2, (size - icon.height) // 2),
            )
            self._cache[key] = ImageTk.PhotoImage(badge, master=self.master)
        return self._cache[key]

    @staticmethod
    def _load_common(name, size, color):
        if name == "windows":
            scale = 4
            image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            gap = max(1, scale)
            margin = 2 * scale
            middle = size * scale // 2
            draw.rectangle((margin, margin, middle - gap, middle - gap), fill=color)
            draw.rectangle((middle + gap, margin, size * scale - margin, middle - gap), fill=color)
            draw.rectangle((margin, middle + gap, middle - gap, size * scale - margin), fill=color)
            draw.rectangle((middle + gap, middle + gap, size * scale - margin, size * scale - margin), fill=color)
            return image.resize((size, size), Image.Resampling.LANCZOS)
        path = ASSET_DIR / ICON_FILES.get(name, "circle-help.png")
        source = Image.open(path).convert("RGBA")
        alpha = source.getchannel("A")
        colored = Image.new("RGBA", source.size, color)
        colored.putalpha(alpha)
        return colored.resize((size, size), Image.Resampling.LANCZOS)

    def _load_ide_image(self, ide_key, executable_path, size):
        source_path = self._official_codex_icon(ide_key, executable_path)
        if source_path is None and executable_path:
            source_path = self._extract_windows_icon(executable_path)
        if source_path and source_path.exists():
            try:
                image = Image.open(source_path).convert("RGBA")
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                result.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
                return self._ensure_contrast(result)
            except OSError:
                pass
        return self._load_common("bot", size, "#657084")

    @staticmethod
    def _ensure_contrast(image):
        visible = [
            pixel for pixel in image.getdata()
            if pixel[3] > 80
        ]
        if not visible:
            return image
        average_luma = sum(
            0.2126 * red + 0.7152 * green + 0.0722 * blue
            for red, green, blue, _alpha in visible
        ) / len(visible)
        if average_luma < 205:
            return image
        backing = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(backing).ellipse(
            (0, 0, image.width - 1, image.height - 1),
            fill="#252a34",
        )
        backing.alpha_composite(image)
        return backing

    @staticmethod
    def _official_codex_icon(ide_key, executable_path):
        if ide_key != "codex" or not executable_path:
            return None
        exe = Path(executable_path)
        try:
            package_root = exe.parents[1]
        except IndexError:
            return None
        candidates = (
            package_root / "assets" / "Square44x44Logo.targetsize-48_altform-unplated.png",
            package_root / "assets" / "icon.png",
        )
        return next((candidate for candidate in candidates if candidate.exists()), None)

    @staticmethod
    def _extract_windows_icon(executable_path):
        return cached_ide_icon(executable_path)
