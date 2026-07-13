"""
将 ChatGPT 生成的两张品牌图拆分成单个文件。
"""
from argparse import ArgumentParser
from pathlib import Path

from PIL import Image
import os


def normalize_bbox(bbox, src_size):
    """AI 给的 0-1000 归一化坐标 → 实际像素"""
    x1, y1, x2, y2 = bbox
    W, H = src_size
    return (
        int(x1 * W / 1000),
        int(y1 * H / 1000),
        int(x2 * W / 1000),
        int(y2 * H / 1000),
    )


def crop_and_save(src_path, bboxes, out_dir, padding=10):
    """按 bbox 列表裁切并保存为 PNG，bbox 是 0-1000 归一化坐标"""
    src = Image.open(src_path)
    src_size = src.size
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for name, bbox in bboxes:
        x1, y1, x2, y2 = normalize_bbox(bbox, src_size)
        # padding（向外扩一点）
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(src_size[0], x2 + padding)
        y2 = min(src_size[1], y2 + padding)
        cropped = src.crop((x1, y1, x2, y2))
        out_path = os.path.join(out_dir, f"{name}.png")
        cropped.save(out_path, "PNG", optimize=True)
        results.append((name, out_path, cropped.size))
        print(f"  [OK] {name:30s} -> {cropped.size}  ->  {out_path}")
    return results


parser = ArgumentParser(description="Split AideLink brand source images into individual assets.")
parser.add_argument("--logo-src", required=True, help="Source image containing logo variants")
parser.add_argument("--assistant-src", required=True, help="Source image containing assistant variants")
parser.add_argument(
    "--out",
    default=str(Path(__file__).resolve().parent),
    help="Output directory for brand assets",
)
args = parser.parse_args()

OUT = Path(args.out)
LOGO_SRC = Path(args.logo_src)
ASST_SRC = Path(args.assistant_src)

# ============================================================
# 1) Logo 源图：6 概念候选 + 5 应用版本 + 1 大图
# ============================================================
print("=" * 60)
print("Logo 源图裁切")
print("=" * 60)
logo_bboxes = [
    # 顶部大展示（左侧 icon + AideLink 文字 + 宣传语）
    ("logo-primary-512-with-wordmark",  [146,  75,  380, 250]),
    # 6 个 LOGO 概念候选（按 AI 返回的顺序）
    ("logo-concept-1-lightarc-bridge",  [486,  32,  634, 159]),
    ("logo-concept-2-dialogue",         [484, 166,  632, 292]),
    ("logo-concept-3-dot-trail",        [486, 297,  634, 423]),
    ("logo-concept-4-open-door",        [486, 431,  634, 554]),
    ("logo-concept-5-fold-interlink",   [486, 563,  634, 689]),
    ("logo-concept-6-code-bridge",      [484, 693,  632, 820]),
    # 5 个 LOGO 应用版本
    ("logo-application-primary-512",    [708,  25,  843, 175]),
    ("logo-application-mark-128",       [706, 175,  843, 269]),
    ("logo-application-horizontal-512x128", [706, 268, 843, 452]),
    ("logo-application-mono-dark",      [706, 454,  843, 545]),
    ("logo-application-mono-light",     [706, 547,  843, 639]),
]
crop_and_save(LOGO_SRC, logo_bboxes, OUT / "logo", padding=8)


# ============================================================
# 2) 小助理源图：1 主立绘 + 4 变体
# ============================================================
print()
print("=" * 60)
print("小助理源图裁切")
print("=" * 60)
# 源图 1536x1024（横向）。左边 ~50% 是主立绘，剩下 50% 上半空、下半是 2x2 变体
# 用 2x2 网格手工估算坐标
ASST_W, ASST_H = 1536, 1024
# 主立绘：左边大块
assistant_bboxes = [
    ("assistant-portrait-main",     [  0,   0,  780, 1024]),  # 左半整块（含"小助理主立绘（半身）"标题）
    # 4 个变体在右下区域，约 x:780-1536, y:540-1024
    ("assistant-variation-smile-point",   [780, 540, 1158, 1024]),
    ("assistant-variation-happy-wink",    [1158, 540, 1536, 1024]),
    ("assistant-variation-thinking",      [780, 1024 - 242, 1158, 1024]),  # 占位，按 2x2 实际调
    ("assistant-variation-cheer-up",       [1158, 1024 - 242, 1536, 1024]),
]
# 重新用更安全的网格切分：4 个变体严格 2x2（直接用像素坐标）
RX1, RX2 = 770, 1536
RY1, RY2 = 540, 1024
mid_x = (RX1 + RX2) // 2
mid_y = (RY1 + RY2) // 2
# 这段是像素值，传入前要"放大"到 0-1000 范围让 normalize_bbox 处理
# 或者直接给 0-1000 比例值
# 源图是 1536x1024，所以 0-1000 范围用 1536/1000=1.536 比例
# 直接给 0-1000 归一化坐标
nx1, nx2 = RX1 * 1000 // 1536, RX2 * 1000 // 1536
ny1, ny2 = RY1 * 1000 // 1024, RY2 * 1000 // 1024
nmid_x = (nx1 + nx2) // 2
nmid_y = (ny1 + ny2) // 2
assistant_bboxes = [
    ("assistant-portrait-main",     [  0,   0,  780 * 1000 // 1536, 1024 * 1000 // 1024]),
    ("assistant-variation-smile-point",  [nx1, ny1,   nmid_x, nmid_y]),
    ("assistant-variation-happy-wink",   [nmid_x, ny1,   nx2, nmid_y]),
    ("assistant-variation-thinking",     [nx1, nmid_y,  nmid_x, ny2]),
    ("assistant-variation-cheer-up",     [nmid_x, nmid_y, nx2, ny2]),
]
crop_and_save(ASST_SRC, assistant_bboxes, OUT / "assistant", padding=4)


print()
print("=" * 60)
print("[DONE] All files saved.")
print("=" * 60)
