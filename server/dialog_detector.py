"""
dialog_detector.py — 通用 IDE 对话面板区域检测引擎

双策略：
  1. 从底部输入框反推（适用于 PrintWindow 捕获的干净窗口截图）
  2. IDE 内置比例启发式（兜底，适用于全屏截图/PrintWindow 不可用时）

对 Electron 应用（Trae / Cursor / VS Code），PrintWindow 通常不可用，
会用 IDE 配置文件中的固定比例裁切 + 列扫描微调。
"""
import numpy as np
from PIL import Image

_INPUT_BOX_VAR_THRESHOLD = 8
_COLUMN_SHIFT_THRESHOLD = 12
_TOP_TRIM_RATIO = 0.08
_BOTTOM_EDGE_MARGIN = 3

# 各 IDE 聊天面板在窗口中的近似比例（左、右百分比）
# 当自动检测失败时用此兜底
IDE_HEURISTIC = {
    "trae": {"left_ratio": 0.38, "right_ratio": 0.58},
    "trae_cn": {"left_ratio": 0.25, "right_ratio": 0.65},
    "agy": {"left_ratio": 0.68, "right_ratio": 0.95},
    "agy2": {"left_ratio": 0.20, "right_ratio": 0.60},
    "oc": {"left_ratio": 0.15, "right_ratio": 0.65},
    "mimo": {"left_ratio": 0.15, "right_ratio": 0.85},
}


def _detect_input_box(arr):
    """从底部向上扫描，找输入框顶部（低方差→高方差的跳变点）"""
    h = arr.shape[0]
    if h < 50:
        return None
    gray = arr.mean(axis=2)
    row_var = gray.std(axis=1)
    scan_bottom = min(h - _BOTTOM_EDGE_MARGIN, h - 1)
    scan_top = int(h * 0.5)
    for y in range(scan_bottom, scan_top, -1):
        if y - 1 < 0 or y >= len(row_var):
            continue
        v_cur, v_prev = float(row_var[y]), float(row_var[y - 1])
        if abs(v_cur - v_prev) > _INPUT_BOX_VAR_THRESHOLD:
            if float(np.mean(row_var[max(0, y):min(h, y + int(h * 0.03))])) < 12:
                return y - 1
    return None


def _detect_panel_edges(arr, input_box_y):
    """在输入框区域扫描列，找左右面板边界"""
    h, w = arr.shape[:2]
    scan_top = max(0, input_box_y - 5)
    scan_bot = min(h, input_box_y + int(h * 0.04))
    region = arr[scan_top:scan_bot, :, :]
    if region.size == 0:
        return None, None
    gray = region.mean(axis=2)
    col_mean = gray.mean(axis=0)
    if len(col_mean) < 3:
        return None, None
    # 从右向左找最左侧的分隔线
    left_edge = None
    for x in range(len(col_mean) - 2, 1, -1):
        if abs(float(col_mean[x]) - float(col_mean[x - 1])) > _COLUMN_SHIFT_THRESHOLD:
            left_edge = x
            break
    if left_edge is None:
        return None, None
    # 向左继续找第二个边界（居中面板场景）
    right_edge = w
    for x in range(left_edge - 1, 1, -1):
        if abs(float(col_mean[x]) - float(col_mean[x - 1])) > _COLUMN_SHIFT_THRESHOLD:
            if abs(x - left_edge) > max(int(w * 0.05), 20):
                right_edge = left_edge
                left_edge = x
                break
    return left_edge, right_edge


def find_dialog_bounds(img, ide_key="trae"):
    """
    检测 IDE 对话面板边界（仅输入框检测策略）。

    返回 (left, top, right, bottom) 或 None。
    只对 PrintWindow 捕获的干净窗口截图有效；
    对全屏截图（Electron 应用）会返回 None，由调用方回退到手动裁剪。
    """
    if img is None or img.width <= 0 or img.height <= 0:
        return None
    w, h = img.width, img.height
    scale = min(400 / max(w, 1), 1.0)
    small = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    m = lambda x: int(x / scale)
    arr = np.array(small.convert("RGB"), dtype=np.float32)
    ib_y = _detect_input_box(arr)
    if ib_y is None or ib_y >= arr.shape[0] - 10:
        return None
    left_e, right_e = _detect_panel_edges(arr, ib_y)
    if left_e is None or right_e is None or right_e - left_e < max(int(arr.shape[1] * 0.05), 20):
        return None
    left, right = m(left_e), m(right_e)
    top = m(int(arr.shape[0] * _TOP_TRIM_RATIO))
    bottom = m(arr.shape[0])
    left = max(0, left); right = min(w, right)
    top = max(0, top); bottom = min(h, bottom)
    if right - left < 100 or bottom - top < 100:
        return None
    return (left, top, right, bottom)


def detect_and_crop(img, ide_key="trae"):
    """检测并裁切对话面板。返回裁切后的 PIL.Image 或 None。"""
    bounds = find_dialog_bounds(img, ide_key)
    if bounds is None:
        return None
    l, t, r, b = bounds
    if r <= l or b <= t:
        return None
    return img.crop((l, t, r, b))

