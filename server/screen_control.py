import os
import sys
import time
import ctypes
from ctypes import wintypes
from paths import SCREEN_CONFIG_FILE
from json_utils import atomic_write_json, safe_read_json

try:
    HWND_BROADCAST = 0xFFFF
    WM_SYSCOMMAND = 0x0112
    SC_MONITORPOWER = 0xF170
    MONITOR_ON = -1
    MONITOR_OFF = 2
    MONITOR_STANDBY = 1
    _has_windows_api = True
except Exception:
    _has_windows_api = False


def load_screen_settings():
    default = {"auto_skip_lock": True}
    data = safe_read_json(SCREEN_CONFIG_FILE, None)
    return data if isinstance(data, dict) else default


def save_screen_settings(settings):
    atomic_write_json(SCREEN_CONFIG_FILE, settings)


def is_screen_locked():
    if not _has_windows_api or not sys.platform.startswith("win"):
        return False
    try:
        try:
            wtsapi32 = ctypes.windll.wtsapi32
            WTSQuerySessionInformation = wtsapi32.WTSQuerySessionInformationW
            WTSFreeMemory = wtsapi32.WTSFreeMemory

            class WTSINFOEX_LEVEL1_W(ctypes.Structure):
                _fields_ = [
                    ("SessionId", wintypes.ULONG),
                    ("SessionState", wintypes.ULONG),
                    ("SessionFlags", wintypes.ULONG),
                ]

            WTSIsSessionLocked = 100
            pBuffer = ctypes.c_void_p()
            bytesReturned = wintypes.DWORD()

            ret = WTSQuerySessionInformation(
                ctypes.c_void_p(0),
                -1,
                ctypes.c_int(WTSIsSessionLocked),
                ctypes.byref(pBuffer),
                ctypes.byref(bytesReturned),
            )
            if ret and pBuffer.value:
                locked = ctypes.cast(pBuffer, ctypes.POINTER(wintypes.ULONG)).contents.value
                WTSFreeMemory(pBuffer)
                return locked == 1
        except Exception:
            pass

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd == 0:
            return True

        try:
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
            title = ctypes.create_unicode_buffer(length)
            ctypes.windll.user32.GetWindowTextW(hwnd, title, length)
            if "lock" in title.value.lower() or "锁屏" in title.value:
                return True
        except Exception:
            pass

        return False
    except Exception as e:
        print(f"[WARN] is_screen_locked failed: {e}", flush=True)
        return False


def wake_screen():
    if not sys.platform.startswith('win'):
        return {'ok': True, 'skipped': True, 'reason': 'not windows'}
    try:
        settings = load_screen_settings()
        if not settings.get('auto_skip_lock', True):
            kernel32 = ctypes.windll.kernel32
            kernel32.SetThreadExecutionState(0x80000001)
            return {'ok': True, 'skipped': True, 'reason': 'auto_skip_lock disabled'}

        print('[INFO] wake_screen: waking display...', flush=True)
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.SetThreadExecutionState(0x80000000 | 0x00000002 | 0x00000001)
        user32.PostMessageW(ctypes.c_void_p(0xFFFF), 0x0112, 0xF170, -1)
        time.sleep(0.5)

        user32.mouse_event(0x0001, 5, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0001, -5, 0, 0, 0)
        time.sleep(0.3)

        user32.keybd_event(0x20, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x20, 0, 2, 0)
        time.sleep(0.5)

        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        user32.SetCursorPos(w // 2, h // 2)
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.8)

        user32.keybd_event(0x0D, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x0D, 0, 2, 0)
        time.sleep(0.8)

        if is_screen_locked():
            print('[INFO] wake_screen: still locked, retrying...', flush=True)
            user32.SetCursorPos(w // 2, h // 2)
            time.sleep(0.1)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.02)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.5)
            user32.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x0D, 0, 2, 0)
            time.sleep(0.8)

        print('[INFO] wake_screen: done', flush=True)
        return {'ok': True, 'woke': True, 'locked': is_screen_locked()}
    except Exception as e:
        print(f'[WARN] wake_screen failed: {e}', flush=True)
        return {'ok': False, 'error': str(e)}


def ensure_screen_unlocked():
    if not _has_windows_api or not sys.platform.startswith("win"):
        return False
    try:
        locked = is_screen_locked()
        if locked:
            print(f"[INFO] Screen is locked, waking it up...", flush=True)
            wake_screen()
            time.sleep(0.5)
            return True
        return False
    except Exception as e:
        print(f"[WARN] ensure_screen_unlocked failed: {e}", flush=True)
        return False


def get_screen_status():
    if not _has_windows_api or not sys.platform.startswith("win"):
        return {"locked": False, "platform": sys.platform, "supported": False}
    try:
        settings = load_screen_settings()
        return {
            "locked": is_screen_locked(),
            "platform": sys.platform,
            "supported": True,
            "auto_skip_lock": settings.get("auto_skip_lock", True)
        }
    except Exception as e:
        return {"locked": False, "platform": sys.platform, "supported": True, "error": str(e)}
