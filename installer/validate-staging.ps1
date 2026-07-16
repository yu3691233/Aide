[CmdletBinding()]
param(
    [string]$StagingDir = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $StagingDir) { $StagingDir = Join-Path $scriptRoot "staging\AideLink" }
$python = Join-Path $StagingDir "runtime\python.exe"
if (-not (Test-Path $python)) { $python = Join-Path $StagingDir "runtime\Scripts\python.exe" }
$server = Join-Path $StagingDir "server"
$managerWorkerSkill = Join-Path $StagingDir "skills\aidelink-manager-worker\SKILL.md"

if (-not (Test-Path $python)) { throw "缺少内置 Python: $python" }
if (-not (Test-Path (Join-Path $server "start_services.py"))) { throw "缺少服务启动入口" }
if (-not (Test-Path (Join-Path $server "start_services.vbs"))) { throw "缺少 Windows 启动入口" }
if (-not (Test-Path $managerWorkerSkill)) { throw "缺少 AideLink 经理/员工协作技能" }

& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw "内置 Runtime 依赖存在冲突" }

$probe = & $python -c "import flask, PIL, pystray, psutil, requests, numpy; import sys; sys.path.insert(0, r'$server'); import routes.ide_routes, routes.screenshot_routes; print('runtime-ok')"
if ($LASTEXITCODE -ne 0 -or $probe -notcontains "runtime-ok") {
    throw "内置 Runtime 缺少服务端关键依赖或路由无法导入"
}

& $python -m compileall -q $server
if ($LASTEXITCODE -ne 0) { throw "服务端 Python 语法编译检查失败" }

$forbidden = @("config.json", "aidelink_settings.json", "manager.pid", "flask_new.log", "phone_app.log")
foreach ($name in $forbidden) {
    if (Test-Path (Join-Path $server $name)) { throw "staging 不应包含用户运行产物: $name" }
}

$forbiddenDirectories = @("worktrees", "scratch", "queues", "results")
foreach ($name in $forbiddenDirectories) {
    if (Test-Path (Join-Path $server $name)) { throw "staging 不应包含开发或运行目录: $name" }
}

$forbiddenArtifacts = @(
    "screen.png", "screen_out.png", "screen_now.png", "screen_now2.png", "screen_now3.png",
    "screen_now4.png", "screen_now5.png", "screen_now6.png", "screen_now7.png", "screen_now8.png",
    "screen_now9.png", "full_logcat.txt", "full_logcat2.txt", "all_logcat.txt", "chat_history.json",
    "project_map.json", "screenshot_crops.json"
)
foreach ($artifact in $forbiddenArtifacts) {
    $matches = Get-ChildItem -LiteralPath $server -Recurse -Force -File -Filter $artifact -ErrorAction SilentlyContinue
    if ($matches) { throw "staging 不应包含开发产物: $($matches[0].FullName)" }
}

# compileall/import checks may create bytecode caches; never ship them.
Get-ChildItem -LiteralPath $StagingDir -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName.Length } -Descending |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $StagingDir -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force
Get-ChildItem -LiteralPath $StagingDir -Recurse -Force -File -Filter "*.whl" -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host "Staging 验证通过: $StagingDir" -ForegroundColor Green
