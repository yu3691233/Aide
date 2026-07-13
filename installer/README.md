# Windows 安装包原型

`AideLink.iss` 是正式 Windows 安装包的入口，使用 Inno Setup 构建。

发布流水线需要先生成以下 staging 目录：

```text
installer/staging/AideLink/
├─ server/       AideLink 服务端代码和资源
├─ runtime/      内置 Python 运行时或已验证的虚拟环境
└─ start_services.vbs
```

当前仓库仍保留根目录 `install.ps1`，用于开发机和故障排查。安装包不应依赖用户预装 Python、Git 或仓库目录。

生成 staging：

```powershell
.\installer\build-staging.ps1 -Clean
.\installer\validate-staging.ps1
```

安装到测试电脑并启动后，可运行：

```powershell
.\installer\verify-install.ps1
```

它会检查安装文件、`/ping` 健康状态和托盘唯一性。

正式发布使用 Python Embeddable Runtime：

```powershell
.\installer\prepare-embedded-runtime.ps1
.\installer\build-staging.ps1 -Clean -RuntimeSource .\installer\runtime-build
.\installer\validate-staging.ps1
```

这样安装包不依赖构建机的 `pyvenv.cfg` 或系统 Python 路径。

构建前必须在干净 Windows 环境验证：双击安装、启动托盘、健康检查、升级、卸载，以及卸载时保留用户数据。
