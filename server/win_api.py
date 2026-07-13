import os
import sys
import ctypes
from ctypes import wintypes
from paths import BRIDGE_DIR

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_monitor_for_window(hwnd):
    try:
        monitors = get_all_monitors()
        if not monitors:
            return None
        monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
        if monitor:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                mx, my = mi.rcMonitor.left, mi.rcMonitor.top
                for m in monitors:
                    if m["x"] == mx and m["y"] == my:
                        return m["name"]
        return monitors[0]["name"] if monitors else None
    except Exception:
        return None


def get_all_monitors():
    monitors = []
    try:
        EnumDisplayMonitors = ctypes.windll.user32.EnumDisplayMonitors
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM
        )

        def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                r = mi.rcMonitor
                monitors.append({
                    "name": f"Monitor-{len(monitors)+1}",
                    "x": r.left,
                    "y": r.top,
                    "width": r.right - r.left,
                    "height": r.bottom - r.top,
                    "is_primary": bool(mi.dwFlags & 1),
                })
            return True

        EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
    except Exception as e:
        print(f"[WARN] get_all_monitors failed: {e}", flush=True)

    if not monitors:
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            monitors.append({
                "name": "Primary",
                "x": 0, "y": 0,
                "width": w, "height": h,
                "is_primary": True,
            })
        except Exception:
            pass

    return monitors


def get_primary_monitor_bbox():
    monitors = get_all_monitors()
    for m in monitors:
        if m.get("is_primary"):
            return m["x"], m["y"], m["width"], m["height"]
    if monitors:
        m = monitors[0]
        return m["x"], m["y"], m["width"], m["height"]
    return 0, 0, 1920, 1080


def get_window_rect(hwnd):
    try:
        rect = RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        return None


def free_gdi_resources(*objs):
    for obj in objs:
        try:
            if obj:
                ctypes.windll.gdi32.DeleteObject(obj)
        except Exception:
            pass
