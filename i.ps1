# AideLink 快捷安装脚本
# 用法: .\install.ps1 [设备地址]
# 示例: .\install.ps1 192.168.1.23:5555

param(
    [string]$Device = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$AppDir = "$ProjectRoot\AideLink-app"
$ApkPath = "$AppDir\app\build\outputs\apk\debug\app-debug.apk"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AideLink 快捷安装工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查设备连接
Write-Host "[1/4] 检查设备连接..." -ForegroundColor Yellow
if ([string]::IsNullOrWhiteSpace($Device)) {
    $connected = adb devices | Select-String "`tdevice" | Select-Object -First 1
    if (-not $connected) {
        throw "未指定设备，且未发现已连接设备。请先运行 adb connect <ip:port>，或传入设备地址。"
    }
    $Device = ($connected.ToString() -split "\s+")[0]
}
$devices = adb devices 2>&1
if ($devices -notmatch $Device) {
    Write-Host "  设备 $Device 未连接，尝试连接..." -ForegroundColor Gray
    adb connect $Device 2>&1 | Out-Null
    Start-Sleep -Seconds 2
}
Write-Host "  设备已连接: $Device" -ForegroundColor Green

# 2. 构建 APK
Write-Host "[2/4] 构建 APK..." -ForegroundColor Yellow
Push-Location $AppDir
try {
    & .\gradlew.bat assembleDebug --no-daemon --quiet 2>&1 | Out-Null
    if (-not (Test-Path $ApkPath)) {
        throw "APK 构建失败"
    }
    Write-Host "  构建成功" -ForegroundColor Green
} finally {
    Pop-Location
}

# 3. 安装 APK
Write-Host "[3/4] 安装到手机..." -ForegroundColor Yellow
$result = adb -s $Device install -r $ApkPath 2>&1
if ($result -match "Success") {
    Write-Host "  安装成功" -ForegroundColor Green
} else {
    Write-Host "  签名不匹配，尝试卸载后重装..." -ForegroundColor Gray
    adb -s $Device uninstall cc.aidelink.app 2>&1 | Out-Null
    $result = adb -s $Device install -r $ApkPath 2>&1
    if ($result -match "Success") {
        Write-Host "  安装成功" -ForegroundColor Green
    } else {
        throw "安装失败: $result"
    }
}

# 4. 启动应用
Write-Host "[4/4] 启动应用..." -ForegroundColor Yellow
adb -s $Device shell am start -n cc.aidelink.app/.MainActivity 2>&1 | Out-Null
Write-Host "  已启动" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  完成! AideLink 已安装并启动" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
