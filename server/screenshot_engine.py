"""
截图引擎 - 从 phone_chat_bridge.py 提取的截图相关函数
合并了 screenshot.py 和 capture_window.py 的功能
"""
import os
import io
import gc
import time
import ctypes
import hashlib
from ctypes import wintypes

from paths import BRIDGE_DIR, STATE_DIR
from json_utils import safe_read_json, safe_write_json
from PIL import Image, ImageDraw, ImageGrab

CROPS_FILE = os.path.join(STATE_DIR, "screenshot_crops.json")


# ============================================================
# ctypes 结构体
# ============================================================

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


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", ctypes.c_ulong),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001


# ============================================================
# 文件 I/O
# ============================================================

def read_crops():
    """读取裁剪配置，支持新旧两种格式，具备防止读写冲突数据丢失的健壮恢复机制"""
    default_crops = {
        "trae": {"left": 300, "right": 350, "top": 30, "bottom": 35, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None},
        "trae_cn": {"left": 300, "right": 350, "top": 30, "bottom": 35, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None},
        "antigravity_ide": {"left": 0, "right": 0, "top": 30, "bottom": 100, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None},
        "oc": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None},
        "codex": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None},
        "mimo": {"left": 0, "right": 0, "top": 0, "bottom": 0, "dialog_position": "center", "calib_width": 0, "calib_height": 0, "focus_input_enabled": False, "input_region": None}
    }
    
    # 如果文件不存在，初始化默认数据并落盘
    if not os.path.exists(CROPS_FILE):
        monitors_data = {
            "monitors": {
                "default": default_crops
            }
        }
        write_crops(monitors_data)
        return monitors_data

    # 读取文件
    try:
        data = safe_read_json(CROPS_FILE, None)
    except Exception:
        data = None

    if not data or not isinstance(data, dict):
        # 读取失败或文件损坏，决不能自动覆盖写盘（以防并发读写导致数据清空）
        # 返回带有 default 配置的结构体供程序运行，但不写入磁盘覆盖旧数据
        print(f"[WARN] screenshot_crops.json is empty or invalid, using temporary default settings without overwriting file", flush=True)
        return {
            "monitors": {
                "default": default_crops
            }
        }

    # 兼容旧格式（以前文件里直接是 {"trae": {...}}，没有 "monitors" 键）
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
                        "focus_input_enabled": False,
                        "input_region": None,
                    }
                    for k, v in data.items()
                }
            }
        }
        write_crops(monitors_data)
        return monitors_data

    # 确保所有条目有 dialog_position/calib 字段
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
                if "focus_input_enabled" not in entry:
                    entry["focus_input_enabled"] = False
                if "input_region" not in entry:
                    entry["input_region"] = None
                # 移除旧的 mode 字段
                entry.pop("mode", None)

    return data


def write_crops(crops):
    safe_write_json(CROPS_FILE, crops)


# ============================================================
# 显示器枚举
# ============================================================

def _stable_monitor_config_key(device_identity, adapter_name=""):
    """把 Windows 的物理显示器接口标识转换为可持久化、不可读出设备信息的键。"""
    identity = str(device_identity or adapter_name or "").strip().casefold()
    if not identity:
        return None
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"monitor_{digest}"


def _get_monitor_device_identity(adapter_name):
    """获取 Windows 为每块物理显示器注册的设备接口名。"""
    if not adapter_name:
        return ""
    try:
        display_device = DISPLAY_DEVICEW()
        display_device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        found = ctypes.windll.user32.EnumDisplayDevicesW(
            adapter_name,
            0,
            ctypes.byref(display_device),
            EDD_GET_DEVICE_INTERFACE_NAME,
        )
        if found:
            return display_device.DeviceID or display_device.DeviceName or adapter_name
    except Exception as exc:
        print(f"[WARN] Failed to resolve monitor device identity for {adapter_name}: {exc}", flush=True)
    return adapter_name


def get_all_monitors():
    """获取所有显示器信息（使用 ctypes，不依赖 pywin32）"""
    monitors = []

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    
    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        try:
            mi = MONITORINFOEXW()
            mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                rc = mi.rcMonitor
                work = mi.rcWork
                is_primary = mi.dwFlags == 1
                adapter_name = mi.szDevice
                device_identity = _get_monitor_device_identity(adapter_name)
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
                    "primary": is_primary,
                    # name 用于当前桌面坐标/切屏；config_key 才是跨主屏切换的物理显示器身份。
                    "config_key": _stable_monitor_config_key(device_identity, adapter_name),
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
    
    # 获取 DPI 缩放因子
    try:
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
            "scale_factor": 1.0,
            "config_key": None,
        }]
    
    return monitors


def _resolve_monitor_storage(monitor_name, current_monitors=None):
    """返回稳定持久化键及当前拓扑下可兼容读取的旧键。"""
    requested = str(monitor_name or "default").strip() or "default"
    if requested == "default" or requested.startswith("monitor_"):
        return requested, []

    monitors = current_monitors if current_monitors is not None else get_all_monitors()
    monitor = next((item for item in monitors if item.get("name") == requested), None)
    if not monitor:
        return requested, []

    stable_key = monitor.get("config_key") or requested
    legacy_keys = [requested] if stable_key != requested else []
    return stable_key, legacy_keys


def get_monitor_for_window(hwnd):
    """获取窗口所在的显示器标识"""
    try:
        user32 = ctypes.windll.user32
        hmon = user32.MonitorFromWindow(hwnd, 2)
        if hmon:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                if mi.dwFlags == 1:
                    return "primary"
                return f"ext_{mi.rcMonitor.left}_{mi.rcMonitor.top}"

        rect = _get_window_rect(hwnd)
        if not rect:
            return "default"
        
        left, top, right, bottom = rect
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        
        monitors = get_all_monitors()
        
        for mon in monitors:
            if (mon["left"] <= center_x < mon["right"] and 
                mon["top"] <= center_y < mon["bottom"]):
                return mon["name"]
        
        return "default"
    except Exception as e:
        print(f"[WARN] get_monitor_for_window failed: {e}", flush=True)
        return "default"


# ============================================================
# 裁剪配置
# ============================================================

def _get_scaled_dims(w, h, max_width=2560, max_height=1440):
    if w <= max_width and h <= max_height:
        return w, h
    ratio = min(max_width / w, max_height / h)
    return int(w * ratio), int(h * ratio)


def get_scaled_crop_config(target, monitor_name=None):
    """获取指定目标的裁剪配置，并将其转换为 scaled 像素值返回给客户端"""
    cfg = get_crop_config(target, monitor_name)
    phys_w = cfg.get("calib_width", 0)
    phys_h = cfg.get("calib_height", 0)

    try:
        win = _find_target_window(target)
        if win:
            import capture_window
            img = capture_window.capture_window_winrt(win._hWnd, client_only=True)
            if img is None:
                img = capture_window.capture_window_client(win._hWnd)
            if img is not None:
                phys_w, phys_h = img.size
                _free_gdi_resources(img)
    except Exception:
        pass

    if phys_w > 0 and phys_h > 0:
        scaled_w, scaled_h = _get_scaled_dims(phys_w, phys_h)
        scale_x = float(scaled_w) / phys_w
        scale_y = float(scaled_h) / phys_h
        
        # 先在物理坐标系下进行动态偏移调整
        adj_l, adj_r, adj_t, adj_b = _adjust_crop_margins(cfg, phys_w, phys_h)
        
        return {
            "left": int(adj_l * scale_x),
            "right": int(adj_r * scale_x),
            "top": int(adj_t * scale_y),
            "bottom": int(adj_b * scale_y),
            "dialog_position": cfg.get("dialog_position", "center"),
            "calib_width": scaled_w,
            "calib_height": scaled_h,
            "focus_input_enabled": cfg.get("focus_input_enabled", False),
            "input_region": cfg.get("input_region"),
        }
    return cfg


def _derive_input_region(cfg, target, monitor_name, monitors):
    """当 cfg 没有 input_region 时，优先从任何已校准的显示器推算默认值，
    否则从 dialog_position + 裁剪边距 推算。

    按物理像素做等比例映射。找不到参考时按 dialog_position 取可见区域中心/偏右/偏左，
    Y 取可见区域底部附近。
    """
    if cfg.get("input_region") is not None:
        return

    calib_w = cfg.get("calib_width", 0) or 0
    calib_h = cfg.get("calib_height", 0) or 0

    # 1. 找任意已保存 input_region 的显示器做参考（排除当前显示器）
    ref = None
    for m_name, m_crops in monitors.items():
        if m_name == monitor_name:
            continue
        mc = m_crops.get(target)
        if mc and mc.get("input_region"):
            ref = mc
            break

    if ref:
        pri_w = ref.get("calib_width", 1) or 1
        pri_h = ref.get("calib_height", 1) or 1
        tgt_w = calib_w if calib_w > 0 else pri_w
        tgt_h = calib_h if calib_h > 0 else pri_h
        pri_in = ref["input_region"]
        cfg["input_region"] = {
            "x": round(min(pri_in["x"] * pri_w / tgt_w, 0.99), 6),
            "y": round(min(pri_in["y"] * pri_h / tgt_h, 0.99), 6),
            "width": 0.01,
            "height": 0.01,
        }
        if not cfg.get("focus_input_enabled") and ref.get("focus_input_enabled"):
            cfg["focus_input_enabled"] = True
        return

    # 2. 没有参考显示器→不推算 Y（Y 必须来自实际校准，不能靠裁剪边距算）。
    #    只推算 X：从 dialog_position 取可见区域水平位置
    if calib_w <= 0 or calib_h <= 0:
        return
    pos = cfg.get("dialog_position", "center")
    left = cfg.get("left", 0)
    right = cfg.get("right", 0)
    vis_w = calib_w - left - right
    if vis_w <= 0:
        return

    if pos == "right":
        x_in_vis = vis_w * 0.75
    elif pos == "left":
        x_in_vis = vis_w * 0.25
    else:
        x_in_vis = vis_w * 0.5

    cfg["input_region"] = {
        "x": round(min((left + x_in_vis) / calib_w, 0.99), 6),
        "y": 0.88,
        "width": 0.01,
        "height": 0.01,
    }


def get_crop_config(target, monitor_name=None):
    """获取指定目标的裁剪配置，按物理显示器隔离并兼容旧坐标键。"""
    crops = read_crops()
    monitors = crops.get("monitors", {})

    if not monitor_name:
        monitor_name = "default"

    storage_key, legacy_keys = _resolve_monitor_storage(monitor_name)
    lookup_keys = [storage_key, *legacy_keys]
    monitor_crops = {}
    resolved_key = storage_key
    for key in lookup_keys:
        candidate = monitors.get(key, {})
        if target in candidate:
            monitor_crops = candidate
            resolved_key = key
            break

    if target not in monitor_crops and storage_key != "default":
        default_crops = monitors.get("default", {})
        if target in default_crops:
            return dict(default_crops[target])

    default_entry = {"left": 0, "right": 0, "top": 0, "bottom": 0,
                     "dialog_position": "center", "calib_width": 0, "calib_height": 0,
                     "focus_input_enabled": False, "input_region": None}
    cfg = dict(monitor_crops.get(target, default_entry))
    _derive_input_region(cfg, target, resolved_key, monitors)
    return cfg


def _normalize_input_region(region):
    """校验并规范化客户区内的输入框区域，坐标均为 0..1 比例。"""
    if region is None:
        return None
    if not isinstance(region, dict):
        raise ValueError("输入框区域格式无效")
    try:
        normalized = {name: float(region[name]) for name in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("输入框区域缺少有效坐标") from exc
    if normalized["width"] <= 0 or normalized["height"] <= 0:
        raise ValueError("输入框区域宽高必须大于 0")
    if normalized["x"] < 0 or normalized["y"] < 0:
        raise ValueError("输入框区域不能超出窗口")
    if normalized["x"] + normalized["width"] > 1.000001 or normalized["y"] + normalized["height"] > 1.000001:
        raise ValueError("输入框区域不能超出窗口")
    return {name: round(value, 6) for name, value in normalized.items()}


def get_input_focus_client_point(config, client_width, client_height):
    """返回输入框区域中心在客户区内的像素坐标；未启用或无效时返回 None。

    input_region 的 x/y 为全图比例（显示空间 0..1），
    y 方向使用「到底边固定偏移」策略：先按校准分辨率算出物理像素到底边偏距，
    派发时从当前窗口高度减去该偏距，从而在窗口高度变化时点击位置保持稳定。
    """
    if not config.get("focus_input_enabled"):
        return None
    try:
        region = _normalize_input_region(config.get("input_region"))
    except ValueError:
        return None
    if not region or client_width <= 0 or client_height <= 0:
        return None
    x_ratio = region["x"] + region["width"] / 2
    y_full_ratio = region["y"] + region["height"] / 2  # 全图比例：由上往下

    # 水平：等比缩放（输入框宽度随窗口等比扩展）
    click_x = round(client_width * x_ratio)

    # 垂直：固定到底边偏距
    calib_h = config.get("calib_height", client_height) or client_height
    if calib_h > 0 and client_height != calib_h:
        # 校准时的物理到底边偏距 = calib_h * (1 - y_full_ratio)
        bottom_offset = int(calib_h * (1.0 - y_full_ratio))
        click_y = client_height - bottom_offset
    else:
        # 窗口高度没变或没有校准基线：直接用等比
        click_y = round(client_height * y_full_ratio)

    return click_x, click_y


def set_crop_config(target, left, right, top, bottom, monitor_name=None, dialog_position=None,
                    calib_width=None, calib_height=None, focus_input_enabled=None, input_region=None):
    """设置指定目标的裁剪配置，按显示器隔离，持久化并记录校准时的分辨率"""
    crops = read_crops()

    if "monitors" not in crops:
        crops["monitors"] = {}

    if not monitor_name:
        monitor_name = "default"

    storage_key, legacy_keys = _resolve_monitor_storage(monitor_name)
    if storage_key not in crops["monitors"]:
        crops["monitors"][storage_key] = {}

    existing = crops["monitors"][storage_key].get(target, {})
    if not existing:
        for legacy_key in legacy_keys:
            legacy_entry = crops["monitors"].get(legacy_key, {}).get(target)
            if legacy_entry:
                existing = dict(legacy_entry)
                break

    phys_w = 0
    phys_h = 0
    try:
        win = _find_target_window(target)
        if win:
            import capture_window
            img = capture_window.capture_window_winrt(win._hWnd, client_only=True)
            if img is None:
                img = capture_window.capture_window_client(win._hWnd)
            if img is not None:
                phys_w, phys_h = img.size
                _free_gdi_resources(img)
    except Exception as e:
        print(f"[WARN] Failed to get physical window size: {e}", flush=True)

    if phys_w <= 0:
        phys_w = existing.get("calib_width", 0)
        phys_h = existing.get("calib_height", 0)

    # Preserve the original calibration baseline if it already exists,
    # so _adjust_crop_margins always compares against the first-calibration size.
    orig_calib_w = existing.get("calib_width", 0)
    orig_calib_h = existing.get("calib_height", 0)

    if phys_w > 0 and phys_h > 0 and calib_width and int(calib_width) > 0 and calib_height and int(calib_height) > 0:
        # Scale the client's crop margins from sender's space to physical coordinates
        scale_x = phys_w / float(calib_width)
        scale_y = phys_h / float(calib_height)
        left = int(left * scale_x)
        right = int(right * scale_x)
        top = int(top * scale_y)
        bottom = int(bottom * scale_y)

    # Use the original calibration baseline if set; otherwise set it now.
    if orig_calib_w > 0 and orig_calib_h > 0:
        calib_width = orig_calib_w
        calib_height = orig_calib_h
    elif phys_w > 0 and phys_h > 0:
        calib_width = phys_w
        calib_height = phys_h
    else:
        calib_width = calib_width or existing.get("calib_width", 0)
        calib_height = calib_height or existing.get("calib_height", 0)

    normalized_region = _normalize_input_region(input_region) if input_region is not None else existing.get("input_region")
    focus_enabled = existing.get("focus_input_enabled", False) if focus_input_enabled is None else bool(focus_input_enabled)
    if focus_enabled and not normalized_region:
        raise ValueError("已开启派发前聚焦，请先在截图中标记输入框区域")

    entry = {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "dialog_position": dialog_position or existing.get("dialog_position", "center"),
        "calib_width": int(calib_width) if calib_width else 0,
        "calib_height": int(calib_height) if calib_height else 0,
        "focus_input_enabled": focus_enabled,
        "input_region": normalized_region,
    }

    crops["monitors"][storage_key][target] = entry
    write_crops(crops)
    return entry


def _adjust_crop_margins(cfg, current_w, current_h):
    """
    根据对话框位置和窗口尺寸变化，动态调整裁剪边距。
    边距基于最大化窗口校准，窗口缩小时按 dialog_position 智能吸收差值。

    水平 (dialog_position)：
      - "right": 右边距不动，左边距吸收 delta_w
      - "left":  左边距不动，右边距吸收 delta_w
      - "center": delta_w 平分左右

    垂直：
      - 上边距固定不动（标题栏/工具栏高度不变）
      - 下边距吸收 delta_h（窗口缩小时 bottom 减小，保持可见区域高度）
    """
    left = cfg.get("left", 0)
    right = cfg.get("right", 0)
    top = cfg.get("top", 0)
    bottom = cfg.get("bottom", 0)
    pos = cfg.get("dialog_position", "center")
    calib_w = cfg.get("calib_width", current_w)
    calib_h = cfg.get("calib_height", current_h)

    if calib_w <= 0:
        calib_w = current_w
    if calib_h <= 0:
        calib_h = current_h

    # ── 水平调整 ──
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

    # ── 垂直调整：top 固定，bottom 吸收 ──
    delta_h = current_h - calib_h
    if delta_h != 0:
        bottom = max(0, bottom + delta_h)

    # ── 安全兜底：确保裁剪后至少有 10px 可见区域 ──
    min_visible = 10
    if left + right >= current_w - min_visible:
        overflow = (left + right) - (current_w - min_visible)
        left = max(0, left - overflow)
        if left + right >= current_w - min_visible:
            right = max(0, current_w - left - min_visible)
    if top + bottom >= current_h - min_visible:
        overflow = (top + bottom) - (current_h - min_visible)
        bottom = max(0, bottom - overflow)
        if top + bottom >= current_h - min_visible:
            top = max(0, current_h - bottom - min_visible)

    return left, right, top, bottom


# ============================================================
# 窗口操作
# ============================================================

def _get_virtual_screen_offset():
    try:
        x_min = ctypes.windll.user32.GetSystemMetrics(76)
        y_min = ctypes.windll.user32.GetSystemMetrics(77)
        return x_min, y_min
    except Exception:
        return 0, 0


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


WINDOW_TITLE_KEYWORDS = {
        "antigravity_ide": ["Antigravity"],
        "trae": ["Trae"],
        "mimo": ["MiMoCode", "MC |", "MC "],
        "oc": ["OpenCode"],
        "codex": ["ChatGPT", "Codex", "OpenAI Codex"],
}


def _window_title_matches(target, title):
    keywords = WINDOW_TITLE_KEYWORDS.get(target, [target])
    normalized_title = (title or "").lower()
    return any(keyword.lower() in normalized_title for keyword in keywords)


def _find_target_window(target):
    import pygetwindow as gw
    wins = gw.getAllWindows()
    try:
        from window_binding import find_bound_window
        bound_window = find_bound_window(target, wins)
        if bound_window:
            return bound_window
    except Exception as exc:
        print(f"[WARN] Failed to resolve saved window binding for {target}: {exc}", flush=True)
    # 安装版窗口标题可能变化（尤其 Electron IDE），按已注册 exe 进程兜底。
    try:
        import ide_scanner
        from window_binding import describe_window
        entry = next((i for i in ide_scanner.get_all_ides() if i.get("key") == target), None)
        exe_name = os.path.basename(entry.get("path", "")).lower() if entry else ""
        if exe_name:
            for w in wins:
                if describe_window(w).get("exe_name", "").lower() == exe_name and w.width > 0 and w.height > 0:
                    return w
    except Exception as exc:
        print(f"[WARN] Failed exe fallback for {target}: {exc}", flush=True)
    for w in wins:
        if w.width > 0 and w.height > 0 and _window_title_matches(target, w.title):
            return w
    return None


def _get_primary_monitor_bbox():
    """获取主显示器的 (left, top, right, bottom) 坐标，用于只截主屏"""
    try:
        monitors = get_all_monitors()
        for mon in monitors:
            if mon.get("primary"):
                return (mon["left"], mon["top"], mon["right"], mon["bottom"])
        if monitors:
            m = monitors[0]
            return (m["left"], m["top"], m["right"], m["bottom"])
    except Exception:
        pass
    return None


def _get_image_space_window_rect(target_win):
    rect = _get_window_rect(target_win._hWnd)
    if not rect:
        return None
    x_min, y_min = _get_virtual_screen_offset()
    left, top, right, bottom = rect
    return left - x_min, top - y_min, right - x_min, bottom - y_min


def _get_window_info(target):
    target_win = _find_target_window(target)
    if not target_win:
        return None
    rect = _get_window_rect(target_win._hWnd)
    if not rect:
        return None
    left, top, right, bottom = rect
    return {
        "target": target,
        "title": target_win.title,
        "left": int(left),
        "top": int(top),
        "right": int(right),
        "bottom": int(bottom),
        "width": int(right - left),
        "height": int(bottom - top),
    }


def _activate_target_window(target, focus_input=False):
    target_win = _find_target_window(target)
    if not target_win:
        return False

    user32 = ctypes.windll.user32
    hwnd = target_win._hWnd

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
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



def _maximize_target_window(target):
    """将目标窗口最大化（用于进入边距调整前确保校准基线）"""
    target_win = _find_target_window(target)
    if not target_win:
        return False

    user32 = ctypes.windll.user32
    hwnd = target_win._hWnd

    try:
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    except Exception:
        pass

    try:
        user32.keybd_event(18, 0, 0, 0)
        user32.keybd_event(18, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

    time.sleep(0.5)  # 等待窗口最大化动画完成
    return True


# ============================================================
# 图片处理
# ============================================================

def _scale_for_phone(img, max_width=2560, max_height=1440):
    """缩放图片到手机/平板友好尺寸（宽 ≤ max_width, 高 ≤ max_height）"""
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
    scaled = cropped
    try:
        scaled = _scale_for_phone(cropped)
        with io.BytesIO() as img_io:
            scaled.save(img_io, 'JPEG', quality=quality)
            return img_io.getvalue()
    finally:
        _free_gdi_resources(scaled, cropped if scaled is not cropped else None)


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
    small = None
    try:
        small = img.resize((80, 45))
        extrema = small.getextrema()
        if len(extrema) == 3:
            max_r, max_g, max_b = extrema[0][1], extrema[1][1], extrema[2][1]
            return max(max_r, max_g, max_b) < threshold
    except Exception:
        pass
    finally:
        if small is not None:
            small.close()
    return False


def safe_grab_screen(bbox=None):
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
    scaled = None
    try:
        scaled = _scale_for_phone(img)
        img_io = io.BytesIO()
        scaled.save(img_io, 'JPEG', quality=quality)
        return img_io.getvalue()
    finally:
        _free_gdi_resources(scaled, img)


def _free_gdi_resources(*objs):
    for obj in objs:
        try:
            close = getattr(obj, "close", None)
            if close:
                close()
        except Exception:
            pass
    gc.collect()


def _encode_jpeg(img, quality=85):
    with io.BytesIO() as buf:
        img.save(buf, 'JPEG', quality=quality)
        return buf.getvalue()
