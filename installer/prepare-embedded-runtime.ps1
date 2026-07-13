[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [string]$PythonVersion = "3.12.10"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputDir) { $OutputDir = Join-Path $scriptRoot "runtime-build" }
$zip = Join-Path $env:TEMP "aidelink-python-embed.zip"
$url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"

if (Test-Path $OutputDir) { Remove-Item -LiteralPath $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -LiteralPath $zip -DestinationPath $OutputDir -Force

$pth = Get-ChildItem $OutputDir -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "Embeddable Runtime 缺少 python._pth" }
$pthText = Get-Content $pth.FullName -Raw
if ($pthText -notmatch "(?m)^Lib\\site-packages$") { Add-Content $pth.FullName "`nLib\site-packages" }
if ($pthText -notmatch "(?m)^\.\.\\server$") { Add-Content $pth.FullName "`n..\server" }
if ($pthText -notmatch "(?m)^import site$") { Add-Content $pth.FullName "`nimport site" }

$getPip = Join-Path $env:TEMP "aidelink-get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
$python = Join-Path $OutputDir "python.exe"
& $python $getPip --no-warn-script-location
$sitePackages = Join-Path $OutputDir "Lib\site-packages"
& $python -m pip install --no-cache-dir --target $sitePackages setuptools wheel
& $python -m pip install --no-cache-dir --target $sitePackages -r (Join-Path $scriptRoot "..\server\requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Embedded Runtime 依赖安装失败" }
Write-Host "Embedded Runtime 已准备: $OutputDir"
