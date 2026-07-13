# AideLink 工具脚本

## 测试

```powershell
.\scripts\test.ps1 -Tier fast
.\scripts\test.ps1 -Tier standard
.\scripts\test.ps1 -Tier full
```

分层范围和 Agent 执行约定见 [`docs/developer/testing.md`](../docs/developer/testing.md)。

## 提交前检查

在提交代码前运行此脚本，检查是否有未提交的修改、冲突标记或语法错误。

### Windows (PowerShell)
```powershell
.\scripts\pre-commit-check.ps1
```

### Linux/macOS (Bash)
```bash
bash scripts/pre-commit-check.sh
```

## 快捷安装

将 APK 安装到手机的快捷脚本。

### Windows (PowerShell)
```powershell
.\i.ps1                          # 默认设备
.\i.ps1 192.168.3.31:33445       # 指定设备
```

### Windows (CMD)
```cmd
i                               # 默认设备
i 192.168.3.31:33445            # 指定设备
```

## Git 工作流

详细的 Git 工作流说明请参阅 [docs/git-workflow.md](../docs/git-workflow.md)。
