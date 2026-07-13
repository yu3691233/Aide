"""
capture_window.py — 窗口穿透截取（支持 DirectX/Electron 应用）

三种捕获策略（按优先级）：
1. Windows.Graphics.Capture API（winrt）— 穿透 Electron / DirectX 窗口，首选
2. PrintWindow 客户区截取 — 传统 GDI 兜底
3. PrintWindow 全窗口截取 — 含标题栏
"""
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import threading
from ctypes import wintypes
from PIL import Image

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32

PW_CLIENTONLY = 1
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _get_client_area_origin(hwnd):
    """获取窗口客户区在屏幕坐标系中的位置"""
    try:
        win_rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
            return None
        pt = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return None
        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            return None
        x_off = pt.x - win_rect.left
        y_off = pt.y - win_rect.top
        return (x_off, y_off, client_rect.right, client_rect.bottom)
    except Exception:
        return None


def capture_window_winrt(hwnd, timeout=3.0, client_only=False):
    """
    使用 Windows.Graphics.Capture API 截取窗口（穿透 DirectX/DirectComposition/Electron）。

    这是对 PrintWindow 的补充：PrintWindow 对 Electron 应用（Trae、AGY、Cursor、VS Code）
    返回空白，而此方法通过 WinRT 直接从 DWM 合成缓冲区读取，同样支持遮挡穿透。

    参数:
        hwnd: 窗口句柄
        timeout: 超时秒数
        client_only: True=只截客户区（不含标题栏/边框），False=整个窗口

    返回 PIL.Image（RGB 模式）或 None（超时/失败/API 不可用）。
    """
    if not hwnd:
        return None

    try:
        from windows_capture import WindowsCapture
    except ImportError:
        print("[WARN] capture_window_winrt: windows-capture not installed", flush=True)
        return None

    result = [None]
    ready = threading.Event()
    capture = None

    def on_frame(frame, control):
        try:
            # frame.frame_buffer: BGRA numpy ndarray
            bgr = frame.frame_buffer[:, :, :3]   # BGRA → BGR
            rgb = bgr[:, :, ::-1]                 # BGR → RGB
            img = Image.fromarray(rgb, 'RGB')
            result[0] = img
        except Exception as e:
            print(f"[WARN] capture_window_winrt frame conversion: {e}", flush=True)
        finally:
            control.stop()
            ready.set()

    def on_closed():
        ready.set()

    try:
        capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=False)
        capture.frame_handler = on_frame
        capture.closed_handler = on_closed
        capture.start()

        if not ready.wait(timeout=timeout):
            print(f"[WARN] capture_window_winrt timeout ({timeout}s) for hwnd={hwnd}", flush=True)
            return None

        img = result[0]
        if img is None:
            return None

        if client_only:
            ca = _get_client_area_origin(hwnd)
            if ca:
                x_off, y_off, c_w, c_h = ca
                if x_off >= 0 and y_off >= 0 and c_w > 0 and c_h > 0:
                    if x_off + c_w <= img.width and y_off + c_h <= img.height:
                        img = img.crop((x_off, y_off, x_off + c_w, y_off + c_h))

        return img

    except Exception as e:
        print(f"[WARN] capture_window_winrt error: {e}", flush=True)
        return None

    finally:
        if capture and hasattr(capture, 'close'):
            try:
                capture.close()
            except Exception:
                pass


def _is_all_black(img):
    """快速检测图片是否全黑（PrintWindow 对 DirectX 窗口返回空白）"""
    extrema = img.getextrema()
    return all(ext[0] == 0 and ext[1] == 0 for ext in extrema)


def _cleanup(hbitmap, memory_dc, hdc, hwnd):
    """安全的 GDI 资源清理"""
    if hbitmap:
        gdi32.DeleteObject(hbitmap)
    if memory_dc:
        gdi32.DeleteDC(memory_dc)
    if hdc and hwnd:
        user32.ReleaseDC(hwnd, hdc)


def capture_window_client(hwnd):
    """
    捕获窗口**客户区**内容（不含标题栏/边框），即使被遮挡。

    返回 PIL.Image（RGB 模式）或 None（失败/窗口不支持 DirectX 渲染）。
    """
    if not hwnd:
        return None

    try:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right, rect.bottom
        if w <= 0 or h <= 0:
            return None

        hdc = user32.GetDC(hwnd)
        if not hdc:
            return None

        memory_dc = gdi32.CreateCompatibleDC(hdc)
        if not memory_dc:
            user32.ReleaseDC(hwnd, hdc)
            return None

        hbitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        if not hbitmap:
            _cleanup(None, memory_dc, hdc, hwnd)
            return None

        gdi32.SelectObject(memory_dc, hbitmap)

        # PrintWindow: 0=success, non-zero=fail
        if user32.PrintWindow(hwnd, memory_dc, PW_CLIENTONLY) == 0:
            _cleanup(hbitmap, memory_dc, hdc, hwnd)
            return None

        # 用 GetDIBits 读像素数据
        bmp_info = BITMAPINFO()
        bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmp_info.bmiHeader.biWidth = w
        bmp_info.bmiHeader.biHeight = -h  # top-down
        bmp_info.bmiHeader.biPlanes = 1
        bmp_info.bmiHeader.biBitCount = 32
        bmp_info.bmiHeader.biCompression = 0  # BI_RGB

        pixel_size = w * h * 4
        pixels = ctypes.create_string_buffer(pixel_size)

        if not gdi32.GetDIBits(
            memory_dc, hbitmap, 0, h,
            pixels, ctypes.byref(bmp_info), DIB_RGB_COLORS
        ):
            _cleanup(hbitmap, memory_dc, hdc, hwnd)
            return None

        _cleanup(hbitmap, memory_dc, hdc, hwnd)

        img = Image.frombuffer('RGBA', (w, h), pixels, 'raw', 'BGRA', 0, 1)
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        if _is_all_black(img):
            print(f"[WARN] capture_window_client: PrintWindow returned blank for hwnd={hwnd}", flush=True)
            return None

        return img

    except Exception as e:
        print(f"[WARN] capture_window_client error: {e}", flush=True)
        return None


def capture_window_full(hwnd):
    """
    捕获**整个窗口**（含标题栏/边框），即使被遮挡。

    返回 PIL.Image（RGB 模式）或 None。
    """
    if not hwnd:
        return None

    try:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None

        # GetWindowDC 包含标题栏等非客户区
        hdc = user32.GetWindowDC(hwnd)
        if not hdc:
            return None

        memory_dc = gdi32.CreateCompatibleDC(hdc)
        if not memory_dc:
            user32.ReleaseDC(hwnd, hdc)
            return None

        hbitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        if not hbitmap:
            _cleanup(None, memory_dc, hdc, hwnd)
            return None

        gdi32.SelectObject(memory_dc, hbitmap)

        if user32.PrintWindow(hwnd, memory_dc, 0) == 0:  # 0 = 包含非客户区
            _cleanup(hbitmap, memory_dc, hdc, hwnd)
            return None

        bmp_info = BITMAPINFO()
        bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmp_info.bmiHeader.biWidth = w
        bmp_info.bmiHeader.biHeight = -h
        bmp_info.bmiHeader.biPlanes = 1
        bmp_info.bmiHeader.biBitCount = 32
        bmp_info.bmiHeader.biCompression = 0

        pixel_size = w * h * 4
        pixels = ctypes.create_string_buffer(pixel_size)

        if not gdi32.GetDIBits(
            memory_dc, hbitmap, 0, h,
            pixels, ctypes.byref(bmp_info), DIB_RGB_COLORS
        ):
            _cleanup(hbitmap, memory_dc, hdc, hwnd)
            return None

        _cleanup(hbitmap, memory_dc, hdc, hwnd)

        img = Image.frombuffer('RGBA', (w, h), pixels, 'raw', 'BGRA', 0, 1)
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        if _is_all_black(img):
            print(f"[WARN] capture_window_full: PrintWindow returned blank for hwnd={hwnd}", flush=True)
            return None

        return img

    except Exception as e:
        print(f"[WARN] capture_window_full error: {e}", flush=True)
        return None
