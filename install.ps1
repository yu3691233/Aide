# install.ps1 - AideLink Bridge 一键安装脚本
#
# 用法（远程）:
#   irm https://raw.githubusercontent.com/yuto0118/AideLink/main/install.ps1 | iex
#
# 用法（本地）:
#   .\install.ps1
#   .\install.ps1 -Port 5000 -OpenFirewall -AutoStart
#
# 参数:
#   -InstallDir    安装目录，未传则交互式询问（默认当前目录或 ~/AideLink）
#   -RepoUrl       仓库地址，默认官方仓库
#   -Port          Bridge 端口，默认 5000
#   -OpenFirewall  自动添加 Windows 防火墙入站规则
#   -AutoStart     注册开机自启（任务计划程序）

[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [string]$RepoUrl = "https://github.com/yu3691233/Aide.git",
    [int]$Port = 5000,
    [switch]$OpenFirewall,
    [switch]$AutoStart
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [OK] $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERR] $msg" -ForegroundColor Red }

function New-AideLinkDesktopShortcut($installPath, $pythonPath) {
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (-not $desktop) { throw "无法定位当前用户桌面目录" }

    $shortcutPath = Join-Path $desktop "AideLink.lnk"
    $serverDir = Join-Path $installPath "server"
    $startScript = Join-Path $serverDir "start_services.py"
    $pythonwPath = Join-Path (Split-Path -Parent $pythonPath) "pythonw.exe"
    if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
        $pythonwPath = $pythonPath
    }

    $iconPath = Join-Path $installPath "installer\AideLink.ico"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonwPath
    $shortcut.Arguments = ('"{0}"' -f $startScript)
    $shortcut.WorkingDirectory = $serverDir
    $shortcut.Description = "启动 AideLink 桌面服务"
    $shortcut.IconLocation = if (Test-Path -LiteralPath $iconPath -PathType Leaf) { $iconPath } else { "shell32.dll,238" }
    $shortcut.Save()

    if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
        throw "桌面快捷方式创建后未找到: $shortcutPath"
    }
    return $shortcutPath
}

function Get-NormalizedPath($path) {
    if (-not $path) { return $null }
    return [IO.Path]::GetFullPath($path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Test-AideLinkInstall($path) {
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Container)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $path "install.ps1") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $path "server\start_services.py") -PathType Leaf)
}

function Find-OldInstallPaths($targetPath) {
    $target = Get-NormalizedPath $targetPath
    $candidates = @((Join-Path $env:USERPROFILE "AideLink"))
    $task = Get-ScheduledTask -TaskName "AideLink Bridge" -ErrorAction SilentlyContinue
    if ($task) {
        foreach ($action in $task.Actions) {
            if ($action.WorkingDirectory) {
                $candidates += Split-Path -Parent (Get-NormalizedPath $action.WorkingDirectory)
            }
        }
    }
    return $candidates |
        Where-Object { $_ } |
        ForEach-Object { Get-NormalizedPath $_ } |
        Where-Object { $_ -ne $target -and (Test-AideLinkInstall $_) } |
        Select-Object -Unique
}

function Stop-ExistingInstall($path) {
    schtasks /End /TN "AideLink Bridge" 2>$null | Out-Null
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.CommandLine -and $_.CommandLine.IndexOf($path, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($_.ExecutablePath -and $_.ExecutablePath.IndexOf($path, [StringComparison]::OrdinalIgnoreCase) -ge 0)
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
}

# 交互式选择安装目录（仅当未显式传入 -InstallDir）
if (-not $InstallDir) {
    $defaultDir = if ($PSScriptRoot) { $PSScriptRoot } else { Join-Path $env:USERPROFILE "AideLink" }
    $input = Read-Host "安装目录 (Enter 使用默认: $defaultDir)"
    $InstallDir = if ($input.Trim()) { $input.Trim() } else { $defaultDir }
}
$InstallDir = Get-NormalizedPath $InstallDir

# 迁移到新目录时，先识别并清理其它位置的一键安装版本。
# 删除前要求人工确认，并严格校验 AideLink 标志文件，避免误删普通目录。
$oldConfigJson = $null
$oldInstallPaths = @(Find-OldInstallPaths $InstallDir)
foreach ($oldPath in $oldInstallPaths) {
    Write-Step "检测到其它位置的旧 AideLink 安装: $oldPath"
    $answer = Read-Host "是否停止旧服务并删除该目录？配置会在需要时迁移到新目录（输入 Y 确认）"
    if ($answer -notmatch '^y(?:es)?$') {
        Write-Step "已保留旧安装: $oldPath"
        continue
    }
    $oldConfigPath = Join-Path $oldPath "server\config.json"
    if (-not $oldConfigJson -and (Test-Path -LiteralPath $oldConfigPath -PathType Leaf)) {
        $oldConfigJson = Get-Content -LiteralPath $oldConfigPath -Raw
    }
    Stop-ExistingInstall $oldPath
    Unregister-ScheduledTask -TaskName "AideLink Bridge" -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $oldPath -Recurse -Force
    Write-OK "旧安装已清理: $oldPath"
}

Write-Step "AideLink Bridge 一键安装"
Write-Step "  InstallDir: $InstallDir"
Write-Step "  Port: $Port"
Write-Step "  OpenFirewall: $OpenFirewall"
Write-Step "  AutoStart: $AutoStart"
Write-Host ""

# === 1. 环境检查 + 自动安装 ===
Write-Step "[1/7] 检查环境（Python + git）..."
$py = Get-Command python -ErrorAction SilentlyContinue
$git = Get-Command git -ErrorAction SilentlyContinue

function Install-Python {
    Write-Step "Python 未安装或不可用，通过 winget 自动安装..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { throw "winget 不可用，请手动下载安装 Python https://www.python.org/downloads/" }
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Python 安装失败，请手动安装" }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

# 检测 Python：有命令且能正常运行才算可用
$pythonCommand = $null
if ($py) {
    $probe = & python -c "import sys; print(sys.executable); print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $probe.Count -ge 2 -and [double]$probe[1] -ge 3.10 -and $probe[0] -notmatch 'WindowsApps|runtime-build|embedded') { $pythonCommand = @("python") }
}
$pyWorks = [bool]$pythonCommand
if (-not $pyWorks) {
    Install-Python
    $pythonCommand = @("python")
}
if (-not $git) {
    Write-Step "git 未安装，通过 winget 自动安装..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { throw "winget 不可用，请手动安装 git https://git-scm.com/" }
    winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "git 安装失败，请手动安装" }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $git = Get-Command git -ErrorAction SilentlyContinue
}
$pythonArgs = if ($pythonCommand.Count -gt 1) { @($pythonCommand[1..($pythonCommand.Count-1)]) } else { @() }
$pyVer = & $pythonCommand[0] @pythonArgs -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pyVer -lt [version]"3.10") {
    throw "Python >= 3.10 required, 当前 $pyVer"
}
Write-OK "Python $pyVer + git OK"
$tkTest = & $pythonCommand[0] @pythonArgs -c "import tkinter; print('ok')" 2>$null
if ($LASTEXITCODE -ne 0 -or $tkTest -ne 'ok') { throw "当前 Python 缺少 tkinter，请安装 python.org 完整版 Python 后重试。" }

# === 2. 克隆/更新仓库 ===
Write-Step "[2/7] 准备仓库 $InstallDir ..."
if (Test-Path $InstallDir) {
    if (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Step "目录已存在，执行 git pull"
        Push-Location $InstallDir
        git pull --ff-only
        $pullCode = $LASTEXITCODE
        Pop-Location
        if ($pullCode -ne 0) { throw "git pull 失败" }
    } else {
        $backup = "{0}.backup-{1}" -f $InstallDir, (Get-Date -Format "yyyyMMdd-HHmmss")
        Write-Step "现有目录不是 Git 仓库，备份到 $backup 后重新克隆"
        Stop-ExistingInstall $InstallDir
        Move-Item -LiteralPath $InstallDir -Destination $backup
        git clone $RepoUrl $InstallDir
        if ($LASTEXITCODE -ne 0) { throw "git clone 失败" }
    }
} else {
    git clone $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { throw "git clone 失败" }
}
Write-OK "仓库就绪"

# === 3. 创建独立运行环境并装依赖 ===
Write-Step "[3/7] 创建 AideLink 独立 Python 环境 ..."
$venvDir = Join-Path $InstallDir ".venv"
$runtimePython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $runtimePython)) {
    & $pythonCommand[0] @pythonArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $runtimePython)) {
        throw "创建 Python 虚拟环境失败"
    }
}
Write-OK "独立 Python 环境已就绪: $venvDir"

Write-Step "安装 Python 依赖 ..."
Push-Location "$InstallDir\server"
try {
    & $runtimePython -m pip install --upgrade pip --quiet
    $requirementsFile = if (Test-Path -LiteralPath "requirements.lock") { "requirements.lock" } else { "requirements.txt" }
    Write-Step "使用依赖清单: $requirementsFile"
    & $runtimePython -m pip install -r $requirementsFile --quiet
    if ($LASTEXITCODE -ne 0) { throw "依赖安装命令失败" }
} catch {
    Pop-Location
    throw "依赖安装失败: $_"
}
Pop-Location
Write-OK "依赖就绪"

# === 3.5. 持久化服务端口 ===
# start_services.py 会继承当前目录下的运行配置；将安装参数写入 config.json，
# 确保健康检查、防火墙和实际 Flask 监听端口保持一致，同时保留已有配置。
Write-Step "持久化 Bridge 端口 $Port ..."
$configPath = Join-Path $InstallDir "server\config.json"
$config = @{}
if (-not (Test-Path -LiteralPath $configPath) -and $oldConfigJson) {
    Set-Content -LiteralPath $configPath -Value $oldConfigJson -Encoding UTF8
    Write-OK "已从旧安装迁移 config.json"
}
if (Test-Path -LiteralPath $configPath) {
    try {
        $existingConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($existingConfig) {
            foreach ($property in $existingConfig.PSObject.Properties) {
                $config[$property.Name] = $property.Value
            }
        }
    } catch {
        Write-Step "旧 config.json 无法解析，将以端口配置重建"
    }
}
$config["flask_port"] = $Port
$config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-OK "Bridge 端口已写入 config.json"

# === 4. 防火墙（可选）===
if ($OpenFirewall) {
    Write-Step "[4/7] 配置 Windows 防火墙 ..."
    New-NetFirewallRule -DisplayName "AideLink $Port" -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
    Write-OK "防火墙规则已添加（端口 $Port）"
} else {
    Write-Step "[4/7] 跳过防火墙配置（未传 -OpenFirewall）"
}

# === 5. 停止旧服务 ===
Write-Step "[5/7] 停止已有 AideLink 进程 ..."
Push-Location "$InstallDir\server"
try {
    & $runtimePython -c "from manager_utils import kill_existing_processes; kill_existing_processes()"
} catch {
    Write-Step "清理进程失败（可能没有旧实例），继续"
}
Pop-Location
Write-OK "清理完成"

# === 6. 启动服务 ===
Write-Step "[6/7] 启动 AideLink Bridge ..."
Push-Location "$InstallDir\server"
& $runtimePython start_services.py
Pop-Location
Start-Sleep -Seconds 3

# === 7. 健康检查 ===
Write-Step "[7/7] 健康检查 ..."
Start-Sleep -Seconds 3
try {
    $ping = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/ping" -UseBasicParsing -TimeoutSec 5
    $body = $ping.Content | ConvertFrom-Json
    if ($body.status -eq "ok") {
        Write-OK "Bridge 已运行: http://localhost:$Port/"
        $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "以太网*","WLAN*","Ethernet*","Wi-Fi*" -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
        if ($lanIp) {
            Write-OK "局域网访问: http://${lanIp}:$Port/"
        }
    } else {
        throw "Bridge 响应异常"
    }
} catch {
    throw "启动失败，检查日志: $InstallDir\server\flask_new.log。详细错误: $_"
}

# === 8. 开机自启（可选）===
if ($AutoStart) {
    Write-Step "[Bonus] 注册开机自启 ..."
    $startScript = Join-Path $InstallDir "server\start_services.py"
    $action = New-ScheduledTaskAction -Execute $runtimePython -Argument ('"{0}"' -f $startScript) -WorkingDirectory "$InstallDir\server"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName "AideLink Bridge" -Action $action -Trigger $trigger -Force
    Write-OK "开机自启已注册"
}

Write-Step "[Bonus] 创建桌面快捷方式 ..."
$shortcutPath = New-AideLinkDesktopShortcut $InstallDir $runtimePython
Write-OK "桌面快捷方式已创建: $shortcutPath"

Write-Host ""
Write-OK "安装完成！"
Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host "  1. 手机 AideLink App -> 设置 -> 服务地址 -> http://${lanIp}:$Port/"
Write-Host "  2. 发送测试消息验证"
Write-Host ""
