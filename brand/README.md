# AideLink Brand Assets

> 品牌资产目录。**Logo 已定型**（光弧桥接），**小助理已定型**（派蒙风 JK + 小米橘发），**12 张工作状态表情包已就绪**。

---

## Logo

最终选用 **光弧桥接** 形态 —— `<` 和 `>` 两个弧形围合中间一个发光小球，暗示"跨端信号连通"。

### 主 Logo 文件（推荐使用）

| 文件 | 用途 |
|---|---|
| `logo-primary-512-with-wordmark.png` | **主 Logo**（icon + "AideLink" 文字）—— 启动器闪屏、README 顶部、品牌物料 |
| `logo-application-primary-512.png` | 纯 icon（无文字）—— 512px 桌面应用图标 |
| `logo-application-mark-128.png` | 纯 icon 128px —— App 抽屉图标、**任务栏托盘图标** |
| `logo-application-horizontal-512x128.png` | 横版（icon + 文字）—— 文档站页眉 |
| `logo-application-mono-dark.png` | 单色暗底版 |
| `logo-application-mono-light.png` | 单色亮底版 |

### 配色色号

- 主色：暖橘 `#FB923C`
- 辅色：珊瑚粉 `#F472B6`
- 渐变方向：左橘右粉（横版）/ 上橘下粉（方版）

---

## 小助理（Assistant）

二次元 JK 派蒙风，**小米橘双马尾** + 绿眼睛 + 白水手服 + 藏蓝百褶裙 + 橘色领结/发带。

### 主立绘

| 文件 | 用途 |
|---|---|
| `assistant-portrait-main.png` | **主立绘**（正面半身、招手、活泼）—— About 对话框、桌面浮窗、营销物料 |

### 状态变体（4 张基础表情）

| 文件 | 表情 | 用途建议 |
|---|---|---|
| `assistant-variation-smile-point.png` | 微笑指引 | 引导操作时（"点这里"） |
| `assistant-variation-happy-wink.png` | 开心眨眼 | 任务完成 / 鼓励 |
| `assistant-variation-thinking.png` | 专注思考 | AI 处理中 |
| `assistant-variation-cheer-up.png` | 热情加油 | 出错鼓励 / 任务启动 |

### 工作状态表情包（12 张，覆盖任务全生命周期）

`assistant/working-states/` —— 配套 `mascot.py` 状态机使用：

| 状态名 | 文件 | 触发时机 |
|---|---|---|
| 01 received    | `assistant-state-01-received.png`  | 收到手机消息 |
| 02 understanding | `assistant-state-02-understanding.png` | 理解需求中 |
| 03 analyzing   | `assistant-state-03-analyzing.png` | 分析复杂度 |
| 04 choose-ide  | `assistant-state-04-choose-ide.png` | 选择最优 IDE |
| 05 dispatch-free | `assistant-state-05-dispatch-free.png` | 分派给免费模型 |
| 06 dispatch-paid | `assistant-state-06-dispatch-paid.png` | 分派给付费 IDE |
| 07 executing   | `assistant-state-07-executing.png` | 任务执行中 |
| 08 thinking    | `assistant-state-08-thinking.png`  | 思考中 |
| 09 troubleshoot | `assistant-state-09-troubleshoot.png` | 遇到问题 |
| 10 optimizing  | `assistant-state-10-optimizing.png` | 优化中 |
| 11 completed   | `assistant-state-11-completed.png` | 任务完成 |
| 12 idle        | `assistant-state-12-idle.png`      | 待命 / 空闲 |

---

## 已集成到 Server

`server/brand_assets/` 镜像了一份精简版（仅 mascot 实际用到的）：

```
server/brand_assets/
├── assistant-portrait.png          ← 主立绘（fallback）
├── tray-icon.png                   ← 任务栏托盘图标（mark-128）
└── working-states/                 ← 12 张工作状态
    └── assistant-state-01~12-*.png
```

**集成位置**：
- `server/mascot.py` —— Tk 浮窗版（手动 `python mascot.py` 启动）
- `server/mascot_tray.py` —— 浮窗 + pystray 托盘版（推荐启动方式）

两个脚本都：
- ✅ 加载 `brand_assets/` 里的定型资产（不再手绘笑脸）
- ✅ 状态机按 chat_history 自动切换 12 个表情
- ✅ 路径走 `BRIDGE_DIR` 环境变量（**不再硬编码 `C:\Users\mi\bridge`**）
- ✅ 托盘图标用定型 logo

---

## 文件结构

```
brand/
├── README.md                        # 本文件
├── BRIEF.md                         # 设计 brief（给其他 agent 看的）
├── _split.py                        # Logo 拆分脚本（可重跑）
├── _split_working_states.py         # 12 张状态包拆分脚本
├── _archive/                        # 未通过的旧版样本（保留作设计沿革）
│
├── logo/
│   ├── logo-primary-512-with-wordmark.png      ★ 主 Logo
│   ├── logo-application-primary-512.png         主 icon 512
│   ├── logo-application-mark-128.png            icon 128（托盘用）
│   ├── logo-application-horizontal-512x128.png  横版
│   ├── logo-application-mono-dark.png           单色暗底
│   ├── logo-application-mono-light.png          单色亮底
│   ├── logo-concept-1~6-*.png                   6 个概念探索（备查）
│   └── _archive/                                未通过的旧版
│
└── assistant/
    ├── assistant-portrait-main.png              ★ 主立绘
    ├── assistant-variation-smile-point.png       微笑指引
    ├── assistant-variation-happy-wink.png        开心眨眼
    ├── assistant-variation-thinking.png          专注思考
    ├── assistant-variation-cheer-up.png          热情加油
    ├── working-states/                          12 张工作状态
    │   └── assistant-state-01~12-*.png
    └── _archive/                                早期样板（v1）
```

---

## 使用建议

- **App launcher 图标**：`logo-application-primary-512.png`
- **任务栏托盘图标**：`logo-application-mark-128.png`（已用）
- **桌面浮窗主形象**：`assistant-portrait-main.png`（已用）
- **状态机切换**：12 张 working-states（已用）
- **README 头部**：`logo-primary-512-with-wordmark.png`
- **About / 设置页**：`assistant-portrait-main.png`

---

## 后续可补充

- [ ] SVG 矢量版 Logo（小尺寸 / 印刷 / 高 DPI 屏需要）
- [ ] 1024×1024 高清小助理主立绘
- [ ] 状态表情包轮播动效（GIF 化）
- [ ] 多姿态扩展：操作电脑、惊讶、困倦等
- [ ] 启动器闪屏全套

---

**版本**：v1.1（2026-06-13 定型 + 桌面集成）
**维护者**：Mavis + 用户
