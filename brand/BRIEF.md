# AideLink 视觉设计 Brief

> 给其他 AI / 设计师 / 自己跑 Midjourney/即梦/DALL-E 用的完整设计需求说明。
> 接手后请先读 §0（已讨论方向）→ §1（明确划掉的方向，避免重复）→ §2（具体需求）。

---

## 0. 项目一句话

**AideLink** —— PC 端 AI 副驾桥接工具。

把 Android 手机的"指令/截图/剪贴板"和 PC 端的"IDE/AI 助手/桌面"通过 ADB + Flask 桥接起来，让你在手机上随手把任务甩给 PC 上的 AI 团队去执行。

**核心语义**（按重要性排序）：
1. **桥接 / 跨端**（手机 ↔ PC 是首要隐喻）
2. **AI 副驾 / 小助理**（拟人化元素，但走二次元，不是赛博朋克）
3. **快捷 / 实时**（不是冷冰冰的远控，是"贴身助理"那种温度）

---

## 1. 已讨论定的方向（**不要重新探索**，直接落地）

### Logo
- **风格定位**：极简 + 留白 + 几何抽象（参考：**飞书 Lark** 的减法美学 —— 一个抽象剪影 + 大量留白；不堆元素；不上文字）
- **配色**：暖橘 `#FB923C` → 珊瑚粉 `#F472B6` 渐变，**禁止黑色 / 禁止深色背景**
- **品类对标**：**UU 远程、ToDesk** 的"工具属性"感 + **飞书** 的"减法美学"
- **核心要求**：
  - 单 icon 强辨识，32px 缩小不变形
  - 主体只占画面 50% 左右，**留白要大**
  - 主体元素 ≤ 2 个（不能再多）
  - 适用场景：App launcher、桌面托盘（16/32/64px）、Favicon

### 小助理（**注意：叫"小助理"，不叫"吉祥物"**）
- **画风**：二次元日系（**Genshin Impact 派蒙**那种 Q 萌感 + 干净线稿 + cel shading）
- **年龄感**：元气少女（18 岁设定，圆脸大眼，亲和力强）
- **服装**：**JK 制服**（水手服领 + 百褶裙），**不要黑色**（避重）
- **发色**：**小米橘**（浅姜橘色双马尾/丸子头），用头绳/发带呼应
- **眼睛**：大、明亮（推荐绿色或橘色，与 Logo 暖色调呼应）
- **关键设计元素**（**选 1-2 个即可，不要全堆**）：
  - 头戴/手环/项链里带一个**小光点 / 小屏幕**（暗示"AI")
  - 眼睛里有十字光标或加载动画感
  - 手持迷你手机或迷你电脑
  - 头发/衣服带电路纹或数据流
- **构图**：先出 1 张**正面半身立绘**（确认 OK 再出多姿态）
- **背景**：纯色或浅渐变（推荐薄荷绿/奶油色），**不要复杂场景**
- **服装配色建议**（避免和 Logo 撞色，保持"延伸"而非"重复"）：
  - 上衣：白色水手服
  - 裙子：藏蓝/深灰（**非黑色**）
  - 配饰/发带：橘色（呼应 Logo）

---

## 2. **已明确排除的方向**（不要再尝试）

### Logo 排除项
- ❌ **字母 A 路线**（A + 光柱、A + 斜杠组合等）—— 已出过 3 版，用户不喜欢"字母感"
- ❌ **两台设备/方块叠加** —— 撞 ToDesk/Sunlogin 视觉
- ❌ **深色背景 / 黑色元素** —— 违反整体调性
- ❌ **复杂多元素堆叠**（> 2 个核心元素）—— 违反飞书极简美学

### 小助理排除项
- ❌ **赛博朋克 / 重机甲风**
- ❌ **真人照片 / 写实风**
- ❌ **Q 版大头 / 贴纸风**（先立绘，Q 版后议）
- ❌ **黑色服装**

---

## 3. **已生成的样本**（不要重复出，可借鉴或规避）

样本位置：`F:\AideLink\brand\`

### Logo 已出 6 候选（均不通过，仅作参考对比）
- `logo\logo-A-A-with-lightbeam.png` — A 字 + 中央光柱 ❌
- `logo\logo-B-two-squares.png` — 两方块 + 对角光束 ❌
- `logo\logo-C-A-bars-connection.png` — 斜杠 A + 能量点 ❌
- `logo\logo-D-bird-flight.png` — 飞鸟剪影展翅 ❌（"鸟"语义偏弱）
- `logo\logo-E-two-rectangles-spark.png` — 双方块 + 火花 ❌
- `logo\logo-F-assistant-head-bubble.png` — 助理头剪影 + 气泡 ❌

### 小助理已出 1 样板（**OK，可作为基准参考**）
- `assistant\assistant-portrait-sample-v1.png` — 派蒙风 + JK + 小米橘发 ✅ **方向对，先确认这个再出多姿态**

---

## 4. Logo 重新出图建议（**新方向提示**）

既然字母路线砍了、设备路线砍了，可以从以下意象中再探索：

1. **抽象连接 / 数据流** —— 两条弧线在中间汇聚成一个点
2. **对话气泡变形** —— 飞书式几何气泡，但更动态
3. **极简桥梁** —— 一道光弧横跨，弧线两端各有一个小圆点（**最简）
4. **折叠屏/手风琴** —— 暗示"跨设备折叠展开"
5. **打开的窗口/门** —— 暗示"从手机打开 PC 的门"
6. **光点 + 轨迹** —— 一个发光小点 + 一道短弧线（最极简）
7. **括号 `< >` 变形** —— 程序员的"尖括号"风格化

**任何方向请确保**：
- 单色或双色渐变（暖橘 #FB923C → 珊瑚粉 #F472B6）
- 留白 ≥ 50% 画面
- 主体只 1-2 个元素
- 32px 缩略图测试：缩小到 32×32 像素仍然能看出主体

---

## 5. 落地规格

| 文件 | 尺寸 | 用途 | 格式 |
|---|---|---|---|
| `logo-primary-512.png` | 512×512 | 主 Logo，启动器/闪屏 | PNG 透明底 |
| `logo-mark-128.png` | 128×128 | App 图标、托盘、Favicon | PNG 透明底 |
| `logo-horizontal-512x128.png` | 512×128 | README/文档站顶部 | PNG 透明底 |
| `logo-mono-dark.png` | 256×256 | 单色深色场景 | PNG 透明底（**只用品牌色**） |
| `logo-mono-light.png` | 256×256 | 单色浅色场景 | PNG 透明底 |
| `assistant-portrait-primary.png` | 1024×1024 | 小助理主立绘 | PNG 透明底或浅渐变底 |
| `assistant-icon-256.png` | 256×256 | 托盘小图、About 对话框 | PNG 透明底 |

**输出位置**：`F:\AideLink\brand\logo\` 和 `F:\AideLink\brand\assistant\`

---

## 6. 推荐的 AI 出图 Prompt 模板

### Logo Prompt 模板
```
Modern minimalist app icon in Lark/Feishu style aesthetic.
[核心意象，如 "abstract two arcs converging to a glowing point"].
Single warm gradient from orange #FB923C to coral pink #F472B6.
Flat modern design with generous negative space (50%+ white space).
Geometric simplicity, only essential lines, professional SaaS brand icon.
No text, no detailed decorations, scalable from 32px to 512px,
background transparent or pure white.
```

### 小助理 Prompt 模板
```
Anime style cute girl character portrait, Genshin Impact Paimon-inspired aesthetic.
JK school uniform: white sailor-collar blouse and navy blue pleated skirt (no black).
Light ginger orange twintail hair, large bright green or orange eyes, hair ribbons.
Cheerful friendly smile, slight head tilt.
Half-body upper body composition.
Background: soft gradient mint green to cream, no complex scene.
High quality anime illustration, cel shading, vibrant colors, clean lineart.
No text, no watermark.
```

---

## 7. 工作流建议

1. **Logo**：一次出 4-6 个不同方向 → 用户挑 1 个 → 围绕挑中的出 4 个变体（位置/角度/留白微调）→ 落定
2. **小助理**：以 v1 样板为基准（**已 OK**）→ 出 3-4 个微调（不同表情/姿态/服装细节）→ 挑 1 个落定
3. **批量出图**：用 `matrix_generate_image` 走批量（见 `requests` 数组用法），一次给 4-6 个 prompt 拿 4-6 张对比

---

## 8. 联系与上下文

- 用户：Windows 11 + PowerShell，主要用 AI 协作出图
- 沟通偏好：**直接、简短、不喜欢反复给选项**
- 调性：避免"工业感 / 程序员闷骚感"，倾向"**年轻、亲和、有点温度**"
- 已出 6+1 张图，**用户对小助理 v1 方向认可**；对 Logo 走极简意象 + 飞书风的方向认可，但具体形态需要重新探索

---

## 版本

- 建立：2026-06-13
- 由 Mavis 整理
- 用途：交接给其他 AI agent / 设计师 / 自跑出图工具
