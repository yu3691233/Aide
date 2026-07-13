# DevSpace 状态记录

更新时间：2026-07-07

## 当前已验证

- ✅ `open_workspace`：可以打开 `F:\AideLink`
- ✅ `read`：可以读取项目文件，例如 `AGENTS.md`
- ✅ `write`：可以创建 / 覆盖文件，例如 `DEVSPACE_HELLO.md`、`TECH_DEBT.md`

## 当前待处理

- ⚠️ `bash`：此前提示本机没有 Git Bash，暂时不能通过 DevSpace 运行 shell 命令
- ⚠️ 代码搜索：需要 shell 或后续工具稳定后再做全仓库扫描
- ⚠️ Git 操作：暂未验证，需等 shell 可用或单独配置后再做

## 建议

1. 安装 Git for Windows，并确认 `C:\Program Files\Git\bin\bash.exe` 存在。
2. 或在 DevSpace 设置里配置可用 shellPath。
3. 在 shell 可用后，优先执行只读审计：

```powershell
git status --short
rg -n "MINIMAX|API_KEY|C:\\Users\\mi|secure_filename|shell=True|json\.dump|json\.load" server AideLink-app
python -m py_compile server/*.py
```

## 说明

本文件仅用于调试 DevSpace 连接能力，可以在确认开发链路稳定后删除。
