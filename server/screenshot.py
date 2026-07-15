import os
import io
import gc
import time
import ctypes
from ctypes import wintypes

from paths import BRIDGE_DIR, STATE_DIR, ASSETS_DIR
from json_utils import safe_read_json, safe_write_json
from PIL import Image, ImageDraw

CROPS_FILE = os.path.join(STATE_DIR, "screenshot_crops.json")


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


DWMWA_EXTENDED_FRAME_BOUNDS = 9


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def get_all_monitors():
    monitors = []

    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        try:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                rc = mi.rcMonitor
                work = mi.rcWork
                is_primary = mi.dwFlags == 1
                if is_primary:
                    name = "primary"
                else:
                    name = f"ext_{rc.left}_{rc.top}"
                monitors.append({
                    "name": name,
                    "left": rc.left,
                    "top": rc.top,
                    "right": rc.right,
                    "bottom": rc.bottom,
                    "width": rc.right - rc.left,
                    "height": rc.bottom - rc.top,
                    "work_left": work.left,
                    "work_top": work.top,
                    "work_right": work.right,
                    "work_bottom": work.bottom,
                    "primary": is_primary
                })
        except Exception as e:
            print(f"[WARN] Monitor callback failed: {e}", flush=True)
        return True

    try:
        MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_void_p)
        callback_func = MONITORENUMPROC(callback)
        ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_func, 0)
    except Exception as e:
        print(f"[WARN] EnumDisplayMonitors failed: {e}", flush=True)

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        for mon in monitors:
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            point = ctypes.wintypes.POINT(mon["left"] + 10, mon["top"] + 10)
            hmon = ctypes.windll.user32.MonitorFromPoint(point, 2)
            if hmon and ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                mon["scale_factor"] = round(dpi_x.value / 96.0, 2)
            else:
                mon["scale_factor"] = 1.0
    except Exception:
        for mon in monitors:
            mon["scale_factor"] = 1.0

    if not monitors:
        return [{
            "name": "primary",
            "left": 0,
            "top": 0,
            "right": 1920,
            "bottom": 1080,
            "width": 1920,
            "height": 1080,
            "primary": True,
            "scale_factor": 1.0
        }]

    return monitors


def _get_window_rect(hwnd):
    try:
        rect = RECT()
        try:
            dwmapi = ctypes.windll.dwmapi
            if dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect)
            ) == 0:
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass

        user32 = ctypes.windll.user32
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        return None


def _find_target_window(target):
    import pygetwindow as gw
    title_map = {
        "antigravity_ide": ["Antigravity IDE", "Antigravity"],
        "trae": ["TRAE SOLO"],
        "trae_cn": ["TRAE SOLO CN"],
        "mimo": ["MiMoCode", "MC |", "MC "],
        "oc": ["OpenCode"],
        "codex": ["ChatGPT", "Codex", "OpenAI Codex"],
    }
    keywords = title_map.get(target, [target])
    wins = gw.getAllWindows()
    for w in wins:
        if w.width > 0 and w.height > 0:
            for kw in keywords:
                if kw.lower() in w.title.lower():
                    return w
    return None


def _free_gdi_resources(*objs):
    for obj in objs:
        try:
            close = getattr(obj, "close", None)
            if close:
                close()
        except Exception:
            pass
    gc.collect()


def read_crops():
    default_crops = {
        "trae": {"left": 300, "right": 350, "top": 30, "bottom": 35, "dialog_position": "center", "calib_width": 0, "calib_height": 0},
        "antigravity_ide": {"left": 0, "right": 0, "top": 30, "bottom": 100, "dialog_position": "center", "calib_width": 0, "calib_height": 0},
        "oc": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0},
        "codex": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0},
        "mimo": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0}
    }
    data = safe_read_json(CROPS_FILE, default_crops)

    if "monitors" not in data:
        monitors_data = {
            "monitors": {
                "default": {
                    k: {
                        "left": v.get("left", 0),
                        "right": v.get("right", 0),
                        "top": v.get("top", 0),
                        "bottom": v.get("bottom", 0),
                        "dialog_position": "center",
                        "calib_width": 0,
                        "calib_height": 0,
                    }
                    for k, v in default_crops.items()
                }
            }
        }
        write_crops(monitors_data)
        return monitors_data

    for m_name in data.get("monitors", {}):
        for t_name in data["monitors"][m_name]:
            entry = data["monitors"][m_name][t_name]
            if isinstance(entry, dict):
                if "dialog_position" not in entry:
                    entry["dialog_position"] = "center"
                if "calib_width" not in entry:
                    entry["calib_width"] = 0
                if "calib_height" not in entry:
                    entry["calib_height"] = 0
                entry.pop("mode", None)

    return data


def write_crops(crops):
    safe_write_json(CROPS_FILE, crops)


def get_crop_config(target, monitor_name=None):
    crops = read_crops()
    monitors = crops.get("monitors", {})

    if not monitor_name:
        monitor_name = "default"

    monitor_crops = monitors.get(monitor_name, {})

    if target not in monitor_crops and monitor_name != "default":
        default_crops = monitors.get("default", {})
        if target in default_crops:
            return default_crops[target]

    default_entry = {"left": 0, "right": 0, "top": 0, "bottom": 0,
                     "dialog_position": "center", "calib_width": 0, "calib_height": 0}
    return monitor_crops.get(target, default_entry)


def set_crop_config(target, left, right, top, bottom, monitor_name=None, dialog_position=None):
    crops = read_crops()

    if "monitors" not in crops:
        crops["monitors"] = {}

    if not monitor_name:
        monitor_name = "default"

    if monitor_name not in crops["monitors"]:
        crops["monitors"][monitor_name] = {}

    existing = crops["monitors"][monitor_name].get(target, {})
    entry = {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "dialog_position": dialog_position or existing.get("dialog_position", "center"),
        "calib_width": existing.get("calib_width", 0),
        "calib_height": existing.get("calib_height", 0),
    }

    crops["monitors"][monitor_name][target] = entry
    write_crops(crops)
    return entry


def _adjust_crop_margins(cfg, current_w, current_h):
    left = cfg.get("left", 0)
    right = cfg.get("right", 0)
    top = cfg.get("top", 0)
    bottom = cfg.get("bottom", 0)
    pos = cfg.get("dialog_position", "center")
    calib_w = cfg.get("calib_width", current_w)

    if calib_w <= 0:
        calib_w = current_w

    delta_w = current_w - calib_w

    if delta_w != 0:
        if pos == "right":
            left = max(0, left + delta_w)
        elif pos == "left":
            right = max(0, right + delta_w)
        else:
            half = delta_w // 2
            left = max(0, left + half)
            right = max(0, right + delta_w - half)

    return left, right, top, bottom


def _get_virtual_screen_offset():
    try:
        x_min = ctypes.windll.user32.GetSystemMetrics(76)
        y_min = ctypes.windll.user32.GetSystemMetrics(77)
        return x_min, y_min
    except Exception:
        return 0, 0


def _scale_for_phone(img, max_width=2560, max_height=1440):
    w, h = img.size
    if w <= max_width and h <= max_height:
        return img
    ratio = min(max_width / w, max_height / h)
    new_size = (int(w * ratio), int(h * ratio))
    print(f"[_scale_for_phone] {w}x{h} -> {new_size[0]}x{new_size[1]}")
    return img.resize(new_size, Image.LANCZOS)


def _crop_to_bytes(img, left, top, right, bottom, quality=70):
    left = max(0, left)
    top = max(0, top)
    right = min(img.width, right)
    bottom = min(img.height, bottom)
    if right <= left or bottom <= top:
        return None
    cropped = img.crop((left, top, right, bottom))
    cropped_scaled = None
    try:
        cropped_scaled = _scale_for_phone(cropped)
        img_io = io.BytesIO()
        cropped_scaled.save(img_io, 'JPEG', quality=quality)
        img_io.seek(0)
        return img_io.getvalue()
    finally:
        _free_gdi_resources(cropped)
        if cropped_scaled is not cropped and cropped_scaled is not None:
            _free_gdi_resources(cropped_scaled)


def _make_placeholder(msg, w=None, h=None, bbox=None):
    if not w:
        w = int(bbox[2] - bbox[0]) if bbox else 1920
    if not h:
        h = int(bbox[3] - bbox[1]) if bbox else 1080
    if w <= 0: w = 800
    if h <= 0: h = 600
    img = Image.new('RGB', (w, h), color='#161b22')
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), msg, fill='#58a6ff')
    return img


def _is_mostly_black(img, threshold=8):
    try:
        small = img.resize((80, 45))
        extrema = small.getextrema()
        if len(extrema) == 3:
            max_r, max_g, max_b = extrema[0][1], extrema[1][1], extrema[2][1]
            return max(max_r, max_g, max_b) < threshold
    except Exception:
        pass
    return False


def safe_grab_screen(bbox=None):
    from PIL import ImageGrab
    try:
        if bbox:
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
        else:
            img = ImageGrab.grab(all_screens=True)
        if _is_mostly_black(img):
            print('[INFO] safe_grab_screen: detected black screen (monitor off?)', flush=True)
            msg = "AideLink: PC Display Off\n\nTap 'Wake Screen' to turn on"
            placeholder = _make_placeholder(msg, w=img.width, h=img.height)
            _free_gdi_resources(img)
            return placeholder
        return img
    except Exception as e:
        print(f"[WARN] Screen grab failed (bbox={bbox}): {e}. Generating placeholder...", flush=True)
        msg = "AideLink PC Offline / Locked\n\n(Screen grab not available)"
        return _make_placeholder(msg, bbox=bbox)


def _grab_region_bytes(left, top, right, bottom, quality=85):
    if right <= left or bottom <= top:
        return None
    img = safe_grab_screen(bbox=(int(left), int(top), int(right), int(bottom)))
    img = _scale_for_phone(img)
    img_io = io.BytesIO()
    img.save(img_io, 'JPEG', quality=quality)
    img_io.seek(0)
    return img_io.getvalue()


def _activate_target_window(target, focus_input=False):
    target_win = _find_target_window(target)
    if not target_win:
        return False

    user32 = ctypes.windll.user32
    hwnd = target_win._hWnd

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        else:
            user32.ShowWindow(hwnd, 5)
    except Exception:
        pass

    try:
        target_win.activate()
    except Exception:
        pass

    try:
        user32.keybd_event(18, 0, 0, 0)
        user32.keybd_event(18, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
    except Exception:
        pass

    time.sleep(0.35)

    if focus_input:
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'alt', 'i')
            time.sleep(0.2)
        except Exception:
            return False

    return True


def _encode_jpeg(img, quality=85):
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)
    buf.seek(0)
    data = buf.getvalue()
    return data
