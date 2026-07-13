[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\AideLink",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$runtime = Join-Path $InstallDir "runtime\python.exe"
if (-not (Test-Path -LiteralPath $runtime)) { $runtime = Join-Path $InstallDir "runtime\Scripts\python.exe" }
$server = Join-Path $InstallDir "server"

foreach ($path in @($runtime, (Join-Path $server "start_services.py"), (Join-Path $server "manager_tray.py"))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "安装文件缺失: $path" }
}

$ping = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/ping" -TimeoutSec 5
if ($ping.status -ne "ok") { throw "服务健康检查失败: $($ping | ConvertTo-Json -Compress)" }

$trays = @(Get-CimInstance Win32_Process | Where-Object {
    # Only Python processes can be tray entrypoints.  Restricting by process
    # name avoids counting this PowerShell verifier's own command line.
    $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -and
        ($_.CommandLine -match '(manager_tray|tray_app|mascot_tray)\.py')
})
if ($trays.Count -gt 1) {
    throw "检测到多个托盘进程 ($($trays.Count))，请检查旧进程或重启系统"
}

Write-Host "AideLink 安装验证通过" -ForegroundColor Green
Write-Host "安装目录: $InstallDir"
Write-Host "服务地址: http://127.0.0.1:$Port"
Write-Host "托盘进程: $($trays.Count)"
