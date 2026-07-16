[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [string]$RuntimeSource = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputDir) { $OutputDir = Join-Path $scriptRoot "staging\AideLink" }
$repo = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$server = Join-Path $repo "server"
$skills = Join-Path $repo "skills"
if (-not $RuntimeSource) { $RuntimeSource = Join-Path $scriptRoot "runtime-build" }
if (-not (Test-Path (Join-Path $RuntimeSource "python.exe")) -and -not (Test-Path (Join-Path $RuntimeSource "Scripts\python.exe"))) {
    throw "未找到 embedded Runtime，请先运行 prepare-embedded-runtime.ps1，或显式传入 -RuntimeSource。"
}

# Always start from an empty tree.  A stale staging directory can otherwise
# reintroduce removed logs/state when the script is run locally without -Clean.
if (Test-Path $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$serverOut = Join-Path $OutputDir "server"
$runtimeOut = Join-Path $OutputDir "runtime"
$skillsOut = Join-Path $OutputDir "skills"
Copy-Item -LiteralPath $server -Destination $serverOut -Recurse -Force
Copy-Item -LiteralPath $RuntimeSource -Destination $runtimeOut -Recurse -Force
if (Test-Path $skills) {
    Copy-Item -LiteralPath $skills -Destination $skillsOut -Recurse -Force
}

if (-not (Test-Path (Join-Path $runtimeOut "pythonw.exe")) -and -not (Test-Path (Join-Path $runtimeOut "Scripts\pythonw.exe"))) {
    throw "staging 缺少可执行的 pythonw.exe"
}

# Never ship user state, logs, caches, or development-only test artifacts.
foreach ($relative in @(
    "state", "__pycache__", "worktrees", "scratch", "queues", "results",
    "flask_new.log", "phone_app.log", "manager.pid",
    "config.json", "aidelink_settings.json", "aidelink_models.json", "phone_in.txt",
    "static\uploads"
)) {
    $path = Join-Path $serverOut $relative
    if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

# Remove generated artifacts at every depth, not only server root.
Get-ChildItem -LiteralPath $serverOut -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.PSIsContainer -and $_.Name -eq "__pycache__") -or
        (-not $_.PSIsContainer -and $_.Extension -in @(".pyc", ".log", ".bak", ".tmp")) -or
        (-not $_.PSIsContainer -and $_.Name -in @(
            "crash.txt", "inject.log", "devspace_err.log", "devspace_out.log",
            "devspace_stderr.log", "devspace_stdout.log", "devspace_test.log",
            "frpc_run.toml", "frpc_run.ini", "frpc_run.log", "frpc_sg.toml",
            "frpc_sg2.log", "frpc_sg_err.log", "frpc_sg_out.log",
            "evolution_state.json", "evolution_tasks_recovery.json", "failure_clusters.json",
            "failure_memory.json", "workaround_knowledge.json", "device_aliases.json",
            "chat_history.json", "project_map.json", "screenshot_crops.json",
            "screen.png", "screen_out.png", "screen_now.png", "screen_now2.png",
            "screen_now3.png", "screen_now4.png", "screen_now5.png", "screen_now6.png",
            "screen_now7.png", "screen_now8.png", "screen_now9.png",
            "full_logcat.txt", "full_logcat2.txt", "all_logcat.txt", "after_clean_build.txt"
        ))
    } |
    Sort-Object { $_.FullName.Length } -Descending |
    Remove-Item -Force -Recurse

Write-Host "Staging 已生成: $OutputDir"
Write-Host "下一步：使用 Inno Setup 编译 installer\AideLink.iss"
