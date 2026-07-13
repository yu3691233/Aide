"""
精准拆分 12 张工作状态表情包（基于 AI 视觉识别的精确 bbox）
"""
from argparse import ArgumentParser
from pathlib import Path

from PIL import Image

# 0-1000 归一化坐标（基于 AI 视觉识别，只切浅色背景方块，不含文字标签）
bboxes = [
    ("01-received",      [120,  95, 268, 320]),
    ("02-understanding", [350,  95, 505, 320]),
    ("03-analyzing",     [585,  95, 748, 320]),
    ("04-choose-ide",    [822,  95, 985, 320]),
    ("05-dispatch-free", [105, 365, 268, 585]),
    ("06-dispatch-paid", [340, 365, 505, 585]),
    ("07-executing",     [575, 365, 748, 585]),
    ("08-thinking",      [835, 365, 985, 585]),
    ("09-troubleshoot",  [125, 635, 268, 855]),
    ("10-optimizing",    [345, 635, 505, 855]),
    ("11-completed",     [600, 635, 748, 855]),
    ("12-idle",          [820, 635, 985, 855]),
]

parser = ArgumentParser(description="Split the assistant working-state sprite sheet.")
parser.add_argument("src", help="Source sprite sheet path")
parser.add_argument(
    "--out-dir",
    default=str(Path(__file__).resolve().parent / "assistant" / "working-states"),
    help="Output directory for the cropped state images",
)
args = parser.parse_args()

out_dir = Path(args.out_dir)
out_dir.mkdir(parents=True, exist_ok=True)

src = Image.open(args.src)
W, H = src.size  # 1402 x 1122

for name, bbox in bboxes:
    x1, y1, x2, y2 = bbox
    # 归一化 → 像素
    px1 = int(x1 * W / 1000)
    py1 = int(y1 * H / 1000)
    px2 = int(x2 * W / 1000)
    py2 = int(y2 * H / 1000)
    # 安全 padding：左右各内缩 8%（避免相邻格侵入），上下不变
    box_w = px2 - px1
    shrink = int(box_w * 0.08)
    px1 += shrink
    px2 -= shrink
    cropped = src.crop((px1, py1, px2, py2))
    out_path = out_dir / f"assistant-state-{name}.png"
    cropped.save(out_path, "PNG", optimize=True)
    print(f"  [OK] {name:24s} -> {cropped.size}")

print(f"\n[DONE] 12 files written to {out_dir}")
