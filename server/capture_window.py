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
import sys
from ctypes import wintypes
from PIL import Image

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32

PW_CLIENTONLY = 1
DIB_RGB_COLORS = 0


def _capture_border_setting():
    """返回窗口捕获边框策略：支持隐藏时关闭，否则交给系统默认。"""
    # GraphicsCaptureSession.IsBorderRequired 在 Windows 11 可用；Windows 10
    # 上强制传 False 可能导致捕获初始化失败，因此保守回退为 None。
    try:
        version = sys.getwindowsversion()
        if version.major >= 10 and version.build >= 22000:
            return False
    except Exception:
        pass
    return None


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
    blank_frames = [0]
    ready = threading.Event()
    capture = None
    capture_control = None

    def on_frame(frame, control):
        img = None
        try:
            # frame.frame_buffer: BGRA numpy ndarray
            # 注意：Image.fromarray 会引用 numpy 数组的内存，而 numpy
            # 数组又持有 frame 的引用。若不显式拷贝，整个 frame_buffer
            # （4K 窗口约 32MB）会随 Image 对象长期驻留，导致内存泄漏。
            # 用 copy=True 让 PIL 创建独立的像素缓冲区，断开对 numpy
            # 数组的引用，使 frame 可被立即回收。
            bgr = frame.frame_buffer[:, :, :3]   # BGRA → BGR
            rgb = bgr[:, :, ::-1]                 # BGR → RGB
            img = Image.fromarray(rgb, 'RGB').copy()
            # 显式删除局部视图，解除对 frame_buffer 的引用
            del bgr, rgb
            if _is_blank_image(img):
                blank_frames[0] += 1
                # DWM/DirectComposition 刚恢复或最大化窗口时，第一帧可能是纯白。
                # 给合成器几帧时间；连续空白则停止并让调用方走屏幕截图兜底。
                if blank_frames[0] < 5:
                    img.close()
                    return
                print(f"[WARN] capture_window_winrt returned blank frames for hwnd={hwnd}", flush=True)
                img.close()
                control.stop()
                ready.set()
                return
            result[0] = img
        except Exception as e:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
            print(f"[WARN] capture_window_winrt frame conversion: {e}", flush=True)
            control.stop()
            ready.set()
            return
        control.stop()
        ready.set()

    def on_closed():
        ready.set()

    try:
        # Windows 11 支持隐藏捕获边框；Windows 10 保持 None，避免不支持该
        # 属性时初始化失败。若当前运行库仍不接受 False，下面统一回退 None。
        border_setting = _capture_border_setting()
        capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=border_setting)
        capture.frame_handler = on_frame
        capture.closed_handler = on_closed
        # start_free_threaded 返回可等待的控制对象；无论成功、失败还是超时，
        # 都能在 finally 中确认原生 D3D 捕获线程已结束。
        capture_control = capture.start_free_threaded()

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
                        # crop 创建新图像，原图立即 close 释放 24MB 像素内存
                        cropped = img.crop((x_off, y_off, x_off + c_w, y_off + c_h))
                        img.close()
                        img = cropped

        # 清除闭包引用，避免 result[0] 长期持有图像对象
        result[0] = None
        return img

    except Exception as e:
        print(f"[WARN] capture_window_winrt error: {e}", flush=True)
        return None

    finally:
        if capture_control is not None:
            try:
                capture_control.stop()
            except Exception:
                pass
            try:
                capture_control.wait()
            except Exception:
                pass
        if capture is not None:
            # windows-capture 没有 close()；清空回调可切断 native capture
            # 对闭包/result/frame 的潜在引用。
            capture.frame_handler = None
            capture.closed_handler = None


def _is_blank_image(img):
    """检测 PrintWindow 对硬件加速窗口返回的纯黑或纯白空白图。"""
    if img is None or img.width <= 0 or img.height <= 0:
        return True
    # 缩小后检查亮度范围，避免对校准大图逐像素扫描。Electron 窗口失败时
    # 常见结果不仅是全黑，也可能是几乎纯白的客户区。
    gray = sample = None
    try:
        gray = img.convert("L")
        sample = gray.resize((32, 32))
        low, high = sample.getextrema()
        return high <= 4 or low >= 251
    finally:
        if sample is not None:
            sample.close()
        if gray is not None:
            gray.close()


def _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap=None):
    """安全的 GDI 资源清理"""
    if memory_dc and old_bitmap:
        gdi32.SelectObject(memory_dc, old_bitmap)
    if hbitmap:
        if not gdi32.DeleteObject(hbitmap):
            print("[WARN] DeleteObject failed for capture bitmap", flush=True)
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

        old_bitmap = gdi32.SelectObject(memory_dc, hbitmap)

        # PrintWindow: 0=success, non-zero=fail
        if user32.PrintWindow(hwnd, memory_dc, PW_CLIENTONLY) == 0:
            _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)
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
            _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)
            return None

        _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)

        rgba_img = Image.frombuffer('RGBA', (w, h), pixels, 'raw', 'BGRA', 0, 1)
        img = rgba_img.convert('RGB')
        rgba_img.close()

        if _is_blank_image(img):
            print(f"[WARN] capture_window_client: PrintWindow returned blank for hwnd={hwnd}", flush=True)
            img.close()
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

        old_bitmap = gdi32.SelectObject(memory_dc, hbitmap)

        if user32.PrintWindow(hwnd, memory_dc, 0) == 0:  # 0 = 包含非客户区
            _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)
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
            _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)
            return None

        _cleanup(hbitmap, memory_dc, hdc, hwnd, old_bitmap)

        rgba_img = Image.frombuffer('RGBA', (w, h), pixels, 'raw', 'BGRA', 0, 1)
        img = rgba_img.convert('RGB')
        rgba_img.close()

        if _is_blank_image(img):
            print(f"[WARN] capture_window_full: PrintWindow returned blank for hwnd={hwnd}", flush=True)
            img.close()
            return None

        return img

    except Exception as e:
        print(f"[WARN] capture_window_full error: {e}", flush=True)
        return None
