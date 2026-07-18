# AGENTS.md

> AideLink AI Agent 最小上下文。只保留本项目特有规则。

## 项目入口

- `AideLink-app/`：Android 客户端，Kotlin + Compose。
- `server/`：PC 桥接服务，Python Flask。
- `server/routes/`：消息、截图、任务、IDE 管理路由。
- `packages/`：外部或实验集成，修改前先读子目录规则。
- 补充规则：`.github/copilot-instructions.md`。

## 文档分工

- `PROGRESS.md`：当前状态、任务、未解决 Bug。
- `TECH_DEBT.md`：技术债、安全风险、清理项。
- `README.md`：项目说明和启动入口。
- 不把历史日志、长方案、技术债追加到本文。

## 项目规则

- 保持项目简单；开发新功能前先调研成熟产品和开源实现，明确复用、适配、参考或自研方案，能改现成方案就不从零重做。
- 优先复用现有模块，少新增抽象层。
- 代码应模块化、可复用；文件过长或职责过多时优先拆分，避免单文件被 AI 改坏导致功能丢失。
- 拆分必须降低复杂度、减少冲突或提升复用性；不要为了模块化而模块化。
- 修改前先看 `PROGRESS.md` / `TECH_DEBT.md`，确认是否与其他 IDE 工作重叠。
- 对其他 IDE 的改动先判断是否完整；能验证就验证，确认完整后应提交，不要长期留半成品。
- 不写入密钥、私有路径、内网 IP、私有域名、FRP token 或运行产物。
- 大债记录到 `TECH_DEBT.md`，不要擅自扩大战线。

## 验证

设备 / App 验证优先调用 AideLink MCP；MCP 不可用时再退回 ADB 或对应工具链。
