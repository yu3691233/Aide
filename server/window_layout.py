"""
window_layout.py — IDE 窗口自动布局管理

功能：
- 读取/保存窗口布局配置
- 将 IDE 窗口移动到指定显示器的指定位置（左半/右半/全屏/手动坐标）
- 通过 API 供手机端调用
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
from flask import Blueprint, jsonify, request
from json_utils import safe_read_json, safe_write_json

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "window_layout.json"

layout_bp = Blueprint("window_layout", __name__)

# 窗口标题查找关键词（与 phone_chat_bridge 保持一致）
WINDOW_KEYWORDS = {
    "trae": ["TRAE SOLO"],
    "trae_cn": ["TRAE SOLO CN"],
    "agy": ["Antigravity IDE", "Antigravity"],
    "mimo": ["MiMoCode", "MC |", "MC "],
    "oc": ["OpenCode"],
}


def _load_config():
    data = safe_read_json(CONFIG_PATH, default=None)
    if data is not None:
        return data
    return {"layouts": {}}


def _save_config(config):
    safe_write_json(CONFIG_PATH, config)


def _find_window(target):
    """按 target 关键词找窗口"""
    import pygetwindow as gw
    keywords = WINDOW_KEYWORDS.get(target, [target])
    for w in gw.getAllWindows():
        if w.width > 0 and w.height > 0:
            for kw in keywords:
                if kw.lower() in w.title.lower():
                    return w
    return None


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _get_monitors():
    """获取所有显示器信息"""
    monitors = []
    # 替代方案：直接用 screenshot_engine 的 get_all_monitors
    try:
        from screenshot_engine import get_all_monitors
        raw = get_all_monitors()
        for m in raw:
            monitors.append({
                "rect": (m["left"], m["top"], m["right"], m["bottom"]),
                "width": m["width"],
                "height": m["height"],
                "primary": m.get("primary", False),
            })
        return monitors
    except Exception:
        pass
    # 兜底：用虚拟屏幕
    sw = user32.GetSystemMetrics(78)
    sh = user32.GetSystemMetrics(79)
    monitors.append({
        "rect": (0, 0, sw, sh),
        "width": sw,
        "height": sh,
        "primary": True,
    })
    return monitors


def apply_layout(target, position="left-half", monitor_index=0):
    """
    移动并调整 IDE 窗口。

    position:
        "left-half"  — 显示器左半屏
        "right-half" — 显示器右半屏
        "full"       — 显示器全屏
        {"x", "y", "w", "h"} — 精确坐标

    返回: (success: bool, message: str)
    """
    win = _find_window(target)
    if not win:
        return False, f"找不到 {target} 窗口"

    monitors = _get_monitors()
    if monitor_index < 0 or monitor_index >= len(monitors):
        return False, f"显示器索引 {monitor_index} 不存在"

    mon = monitors[monitor_index]
    mx, my = mon["rect"][0], mon["rect"][1]
    mw, mh = mon["width"], mon["height"]

    if position == "left-half":
        x, y, w, h = mx, my, mw // 2, mh
    elif position == "right-half":
        x, y, w, h = mx + mw // 2, my, mw // 2, mh
    elif position == "full":
        x, y, w, h = mx, my, mw, mh
    elif isinstance(position, dict):
        x = mx + position.get("x", 0)
        y = my + position.get("y", 0)
        w = position.get("w", mw)
        h = position.get("h", mh)
    else:
        return False, f"未知位置: {position}"

    hwnd = win._hWnd
    result = user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW
    if result == 0:
        return False, "SetWindowPos 失败"
    return True, f"已将 {target} 移动到 ({x},{y}) {w}x{h}"


# ── API routes ─────────────────────────────────────────────


@layout_bp.route("/api/window-layout", methods=["GET"])
def api_get_layout():
    config = _load_config()
    monitors = _get_monitors()
    # 附带当前窗口状态
    windows = {}
    for ide_key in WINDOW_KEYWORDS:
        w = _find_window(ide_key)
        if w:
            rect = wintypes.RECT()
            if user32.GetWindowRect(w._hWnd, ctypes.byref(rect)):
                windows[ide_key] = {
                    "left": rect.left, "top": rect.top,
                    "right": rect.right, "bottom": rect.bottom,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
    return jsonify({
        "success": True,
        "config": config,
        "monitors": [{"index": i, "rect": m["rect"], "width": m["width"], "height": m["height"], "primary": m["primary"]} for i, m in enumerate(monitors)],
        "windows": windows,
    })


@layout_bp.route("/api/window-layout", methods=["PUT"])
def api_save_layout():
    data = request.json or {}
    layouts = data.get("layouts", {})
    config = {"layouts": layouts}
    _save_config(config)
    return jsonify({"success": True, "config": config})


@layout_bp.route("/api/window-layout/apply", methods=["POST"])
def api_apply_layout():
    data = request.json or {}
    target = data.get("target", "").strip().lower()
    position = data.get("position", "left-half")
    monitor = int(data.get("monitor", 0))

    if target:
        ok, msg = apply_layout(target, position, monitor)
        return jsonify({"success": ok, "message": msg})
    else:
        results = {}
        config = _load_config()
        for t, cfg in config.get("layouts", {}).items():
            ok, msg = apply_layout(t, cfg.get("position", "left-half"), int(cfg.get("monitor", 0)))
            results[t] = {"success": ok, "message": msg}
        return jsonify({"success": True, "results": results})
