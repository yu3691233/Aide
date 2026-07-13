# AideLink

> PC 端 AI 副驾桥接工具：把 Android 手机、PC 桥接服务和桌面 AI/IDE 工作流连起来。

## 项目入口

| 路径 | 说明 |
|---|---|
| `AideLink-app/` | Android 客户端，Kotlin + Compose |
| `server/` | PC 桥接服务，Python Flask |
| `server/routes/` | 消息、截图、任务、IDE 管理等路由 |
| `packages/` | 外部或实验集成，修改前先看子目录说明 |
| `docs/` | 详细文档，部分历史文档可能需要核查时效 |

## 核心能力

- 手机与 PC 之间的消息、截图、剪贴板桥接。
- 通过 PC 服务管理桌面 IDE、任务队列和 AI 派发流程。
- Android App 作为移动控制入口。
- 支持 AideLink MCP 辅助设备发现、安装、启动、日志获取和验证。

## 快速开始

### PC 端

普通用户请从 GitHub Release 下载 `AideLink-Setup.exe`，安装包自带 Python Runtime，不需要预装 Python 或 Git。安装后从开始菜单或桌面快捷方式启动 AideLink。

开发者或需要调试源码时，再使用以下方式：

```powershell
cd server
python start_services.py
```

完整安装、校验、升级和卸载说明见 [`docs/user/installation.md`](docs/user/installation.md)。

### Android 端

在 `AideLink-app/` 构建并安装 debug APK，或通过 AideLink MCP 完成设备连接、安装和验证。

```powershell
cd AideLink-app
.\gradlew.bat assembleDebug --no-daemon
```

## 开发入口

| 文档 | 用途 |
|---|---|
| `AGENTS.md` | AI Agent 最小项目规则 |
| `PROGRESS.md` | 当前项目状态、任务、未解决 Bug |
| `TECH_DEBT.md` | 技术债、安全风险、清理项 |
| `.github/copilot-instructions.md` | Copilot / 手机桥接补充规则 |
| `docs/README.md` | 文档索引 |
| `docs/user/release-acceptance-checklist.md` | Windows 用户机发布验收清单 |

## 当前状态

项目处于持续整理和模块化阶段。新的开发原则是：

- 保持项目简单。
- 优先复用现有模块。
- 文件过长或职责过多时及时拆分，避免单文件承载过多功能。
- 技术债统一记录到 `TECH_DEBT.md`。

## 许可

TBD（待补 LICENSE）。
