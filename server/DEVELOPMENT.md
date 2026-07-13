# Server 开发说明

> 历史版开发文档已过时。本文件只保留当前入口，避免旧私有路径、旧规则文件和旧流程误导后续 Agent。

## 当前入口

| 内容 | 路径 |
|---|---|
| Server 主入口 | `server/phone_chat_bridge.py` |
| 路由模块 | `server/routes/` |
| 任务运行时 | `server/task_runtime.py` |
| 任务派发工具 | `server/dispatch_utils.py` |
| 截图引擎 | `server/screenshot_engine.py` |
| 状态目录 | `server/state/` |

## 开发原则

- 优先复用现有模块。
- 文件过长或职责过多时优先拆分。
- 不写入密钥、私有路径、内网 IP、私有域名或运行产物。
- 技术债记录到根目录 `TECH_DEBT.md`。

## 验证

```powershell
python -m py_compile server/*.py
```
