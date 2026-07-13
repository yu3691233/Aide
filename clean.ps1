# AideLink 一键清理脚本
# 清理所有运行时生成的产物，保留 .py 源码 + .git 仓库
# 在 23 上运行完这个再跑 install.ps1 就相当于全新安装

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = Join-Path $root "server"
$app = Join-Path $root "AideLink-app"

Write-Host "=== AideLink 一键清理 ===" -ForegroundColor Cyan

# 1. 杀掉所有 bridge 相关进程
Write-Host "[1/5] 停止运行中的 bridge 进程..." -ForegroundColor Yellow
Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object {
    $cmd = $_.CommandLine
    $cmd -match "phone_chat_bridge|start_services|frpc|manager" -or $cmd -match "AideLink"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
# 再杀一遍 frpc
Get-Process -Name frpc -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "  OK" -ForegroundColor Green

# 2. 清理 server/ 运行时产物
Write-Host "[2/5] 清理 server/ 运行时产物..." -ForegroundColor Yellow
$serverFiles = @(
    "*.log", "*.pid", "*.bak"
    "chat_history.json", "clipboard_history.json", "scanned_ides.json", "manual_ides.json"
    "evolution_state.json", "evolution_tasks_recovery.json", "failure_memory.json"
    "failure_clusters.json", "token_usage.json", "workaround_knowledge.json"
    "phone_in.txt", "inject.log", "task_context.json.bak"
    "screen_*.png", "screen.png", "screen_out.png", "test.png"
    "ui*.xml", "window_dump.xml", "app_ui*.xml"
    "project_map.json"
    "startup_error.txt", "startup_output.txt", "after_clean_build.txt", "after_tap.txt"
    "mascot_tray_content.txt"
    "notification_watcher_state.json"
    "codex_pre_fix_20260702.patch.txt"
    "all_logcat.txt", "full_logcat*.txt", "logcat.txt"
)
foreach ($pattern in $serverFiles) {
    Get-ChildItem -Path $server -Filter $pattern -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}
# 清理 __pycache__
Get-ChildItem -Path $server -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
# 清理 state/ 目录内容（保留目录本身）
if (Test-Path (Join-Path $server "state")) {
    Get-ChildItem -Path (Join-Path $server "state") -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
# 清理 scratch/
if (Test-Path (Join-Path $server "scratch")) {
    Remove-Item -Path (Join-Path $server "scratch") -Recurse -Force -ErrorAction SilentlyContinue
}
# 清理 results/
if (Test-Path (Join-Path $server "results")) {
    Remove-Item -Path (Join-Path $server "results") -Recurse -Force -ErrorAction SilentlyContinue
}
# 清理 queues/
if (Test-Path (Join-Path $server "queues")) {
    Remove-Item -Path (Join-Path $server "queues") -Recurse -Force -ErrorAction SilentlyContinue
}
# 清理 static/uploads/
$uploads = Join-Path $server "static" "uploads"
if (Test-Path $uploads) {
    Remove-Item -Path "$uploads\*" -Recurse -Force -ErrorAction SilentlyContinue
}
# 清理 frpc_run.log
Get-ChildItem -Path $server -Filter "frpc_run.log" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
# 清理 _ 开头的调试文件
Get-ChildItem -Path $server -Filter "_*.py" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $server -Filter "_*.json" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $server -Filter "_scan_result.json" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $server -Filter "_extracted_messages.json" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  OK" -ForegroundColor Green

# 3. 清理 Android 构建产物
Write-Host "[3/5] 清理 AideLink-app 构建产物..." -ForegroundColor Yellow
$buildDir = Join-Path $app "app" "build"
if (Test-Path $buildDir) {
    Remove-Item -Path $buildDir -Recurse -Force -ErrorAction SilentlyContinue
}
Get-ChildItem -Path $app -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $app -Filter ".gradle" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $app -Filter "local.properties" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  OK" -ForegroundColor Green

# 4. 清理根目录调试文件
Write-Host "[4/5] 清理根目录调试残留..." -ForegroundColor Yellow
Get-ChildItem -Path $root -Filter "screen_*.png" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Filter "window_dump.xml" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Filter "*.log" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Filter "*.pid" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "  OK" -ForegroundColor Green

# 5. 检查剩余关键文件
Write-Host "[5/5] 验证关键文件完整性..." -ForegroundColor Yellow
$keyFiles = @(
    "server\phone_chat_bridge.py",
    "server\routes\__init__.py",
    "server\requirements.txt",
    "install.ps1"
)
$missing = $false
foreach ($f in $keyFiles) {
    $p = Join-Path $root $f
    if (Test-Path $p) {
        Write-Host "  OK   $f" -ForegroundColor Green
    } else {
        Write-Host "  MISS $f" -ForegroundColor Red
        $missing = $true
    }
}

Write-Host ""
if (-not $missing) {
    Write-Host "=== 清理完成！现在可以运行 install.ps1 一键安装了 ===" -ForegroundColor Cyan
    Write-Host "   cd $root" -ForegroundColor White
    Write-Host "   .\install.ps1" -ForegroundColor White
} else {
    Write-Host "=== 警告：部分关键文件缺失，可能仓库不完整 ===" -ForegroundColor Red
}
