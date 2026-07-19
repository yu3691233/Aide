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

        # 唤醒显示器电源：SetThreadExecutionState + 广播 SC_MONITORPOWER MONITOR_ON。
        # 这两个调用不会触发任何 UI 副作用。
        kernel32.SetThreadExecutionState(0x80000000 | 0x00000002 | 0x00000001)
        user32.PostMessageW(ctypes.c_void_p(0xFFFF), 0x0112, 0xF170, -1)
        time.sleep(0.5)

        # 鼠标相对移动 5 像素再移回，足以唤醒屏保/显示器，不会点击任何 UI。
        user32.mouse_event(0x0001, 5, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0001, -5, 0, 0, 0)
        time.sleep(0.3)

        # 注意：之前这里会发送 Space、鼠标右键 + Enter 组合试图解锁锁屏，
        # 但右键 + Enter 会触发系统托盘/前台窗口的上下文菜单并选中第一项，
        # 曾误触 manager_tray 的"重启所有服务"，导致 Flask 服务被杀。
        # 现代 Windows 锁屏需要密码，模拟按键也无法安全解除，已移除。

        print('[INFO] wake_screen: done', flush=True)
        return {'ok': True, 'woke': True, 'locked': is_screen_locked()}
    except Exception as e:
        print(f'[WARN] wake_screen failed: {e}', flush=True)
        return {'ok': False, 'error': str(e)}


def turn_off_monitor():
    """关闭显示器电源（仅发送 SC_MONITORPOWER MONITOR_OFF 广播）。

    供 App 远程测试用：关闭显示器后立即派发任务，验证 wake_screen 能否
    在派发入口被自动触发并点亮显示器完成注入。
    """
    if not _has_windows_api or not sys.platform.startswith("win"):
        return {'ok': False, 'reason': 'not supported on this platform'}
    try:
        user32 = ctypes.windll.user32
        user32.PostMessageW(ctypes.c_void_p(HWND_BROADCAST), WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)
        time.sleep(0.2)
        user32.PostMessageW(ctypes.c_void_p(HWND_BROADCAST), WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)
        print('[INFO] turn_off_monitor: display off command sent', flush=True)
        return {'ok': True}
    except Exception as e:
        print(f'[WARN] turn_off_monitor failed: {e}', flush=True)
        return {'ok': False, 'error': str(e)}


def ensure_screen_unlocked():
    """派发注入前确保屏幕可用（显示器点亮 + 未锁屏）。

    总是调用 wake_screen，因为：
    1. 显示器关闭但未锁屏时（无密码 Windows）is_screen_locked 返回 False，
       但 SetForegroundWindow 仍会失败（GetForegroundWindow 返回 hwnd=0）。
    2. wake_screen 是幂等安全的（仅唤醒显示器电源 + 鼠标移动，无 UI 副作用）。
    """
    if not _has_windows_api or not sys.platform.startswith("win"):
        return False
    try:
        was_locked = is_screen_locked()
        # 无论是否锁屏都尝试唤醒显示器——显示器关闭时 SetForegroundWindow
        # 会失败，必须先点亮显示器才能激活窗口。
        wake_screen()
        if was_locked:
            time.sleep(0.5)
        return True
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
