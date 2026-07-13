# AideLink Git 提交前检查脚本 (PowerShell)
# 检查冲突标记、语法，并运行单元测试
#
# 用法：
#   .\scripts\pre-commit-check.ps1              # fast: server unit + 语法 + 冲突
#   .\scripts\pre-commit-check.ps1 -Tier standard  # + Android JVM + JS 语法
#
# 注意：此脚本不检查"工作区是否干净"——提交前必然有未提交的修改。
# 如需确认工作区干净，请单独运行 `git status`。

param(
    [ValidateSet("fast", "standard", "full")]
    [string]$Tier = "fast"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AideLink 提交前检查 ($Tier)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $ProjectRoot
try {
    # 1. 显示 git status（仅展示，不阻止——提交前必然有修改）
    Write-Host "[1/4] Git 状态..." -ForegroundColor Yellow
    $status = git status --porcelain 2>&1
    if ($status) {
        Write-Host "  当前未提交的修改：" -ForegroundColor Gray
        Write-Host $status
    } else {
        Write-Host "  工作区干净" -ForegroundColor Green
    }
    Write-Host ""

    # 2. 检查冲突标记
    Write-Host "[2/4] 检查冲突标记..." -ForegroundColor Yellow
    $conflicts = Get-ChildItem -Path . -Include *.py,*.kt,*.java -Recurse |
        Select-String -Pattern "<<<<<<" -SimpleMatch -ErrorAction SilentlyContinue
    if ($conflicts) {
        Write-Host "  ❌ 发现冲突标记！" -ForegroundColor Red
        $conflicts | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber)" }
        throw "存在冲突标记，请先解决"
    }
    Write-Host "  ✅ 没有冲突标记" -ForegroundColor Green
    Write-Host ""

    # 3. Python 语法检查（fast 层）
    Write-Host "[3/4] Python 语法检查..." -ForegroundColor Yellow
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $pyFiles = Get-ChildItem -Path server -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
        $hasError = $false
        foreach ($file in $pyFiles) {
            $null = python -m py_compile $file.FullName 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  ❌ $($file.Name) 语法错误" -ForegroundColor Red
                $hasError = $true
            }
        }
        if ($hasError) { throw "Python 语法检查失败" }
        Write-Host "  ✅ Python 语法检查通过" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Python 未安装，跳过语法检查" -ForegroundColor Yellow
    }
    Write-Host ""

    # 4. 单元测试（调用 test.ps1）
    Write-Host "[4/4] 运行单元测试 (tier: $Tier)..." -ForegroundColor Yellow
    & "$PSScriptRoot\test.ps1" -Tier $Tier
    if ($LASTEXITCODE -ne 0) {
        throw "单元测试失败"
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ✅ 检查通过，可以提交" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
}
finally {
    Pop-Location
}
