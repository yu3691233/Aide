# AideLink 半自动冒烟脚本
# 检查服务可达性、关键 API、状态文件 schema、单元测试
#
# 用法：.\scripts\smoke-test.ps1
# 配合：docs/productization/regression-checklist.md

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AideLink 冒烟测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $ProjectRoot
try {
    # 1. 检查 Flask 服务可达性
    Write-Host "[1/4] Flask 服务可达性..." -ForegroundColor Yellow
    $bridgeUrl = $env:AIDELINK_BRIDGE_URL
    if (-not $bridgeUrl) { $bridgeUrl = "http://localhost:5000" }
    try {
        $response = Invoke-RestMethod -Uri "$bridgeUrl/api/desktop-ides" -Method Get -TimeoutSec 5 -ErrorAction Stop
        Write-Host "  ✅ 服务可达 ($bridgeUrl)" -ForegroundColor Green
    } catch {
        Write-Host "  ❌ 服务不可达: $bridgeUrl" -ForegroundColor Red
        Write-Host "  错误: $($_.Exception.Message)" -ForegroundColor Gray
        Write-Host "  请确认 Flask 服务已启动。" -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""

    # 2. 关键 API 端点
    Write-Host "[2/4] 关键 API 端点..." -ForegroundColor Yellow
    $endpoints = @(
        @{ Path = "/api/desktop-ides"; Name = "桌面 IDE 列表" },
        @{ Path = "/api/models"; Name = "模型列表" },
        @{ Path = "/api/projects"; Name = "项目列表" }
    )
    foreach ($ep in $endpoints) {
        try {
            $null = Invoke-RestMethod -Uri "$bridgeUrl$($ep.Path)" -Method Get -TimeoutSec 5 -ErrorAction Stop
            Write-Host "  ✅ $($ep.Name) ($($ep.Path))" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ $($ep.Name) ($($ep.Path)): $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host ""

    # 3. 状态文件 schema
    Write-Host "[3/4] 状态文件 schema..." -ForegroundColor Yellow
    & python -m unittest tests.server.test_state_schema -v 2>&1 | ForEach-Object {
        if ($_ -match "^test_.*\.\.\.\s*(ok|ERROR|FAIL)") {
            $result = $matches[1]
            if ($result -eq "ok") {
                Write-Host "  ✅ $_" -ForegroundColor Green
            } else {
                Write-Host "  ❌ $_" -ForegroundColor Red
            }
        } elseif ($_ -match "^(OK|FAILED|Ran)") {
            Write-Host "  $_" -ForegroundColor Cyan
        }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ 状态文件 schema 校验失败" -ForegroundColor Red
        exit 1
    }
    Write-Host ""

    # 4. 单元测试
    Write-Host "[4/4] 单元测试 (fast tier)..." -ForegroundColor Yellow
    & "$PSScriptRoot\test.ps1" -Tier fast
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ 单元测试失败" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ✅ 冒烟测试全绿" -ForegroundColor Green
    Write-Host "  请继续手动检查: docs/productization/regression-checklist.md" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}
finally {
    Pop-Location
}
