param(
    [ValidateSet("fast", "standard", "full")]
    [string]$Tier = "fast"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    Write-Host "[TEST] $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Push-Location $ProjectRoot
try {
    Invoke-Step "Server unit tests" {
        python -m unittest discover -s tests/server -p "test_*.py" -v
    }

    if ($Tier -in @("standard", "full")) {
        Invoke-Step "Server Python syntax" {
            $files = rg --files server -g "*.py"
            python -m py_compile $files
        }

        if (Get-Command node -ErrorAction SilentlyContinue) {
            Invoke-Step "Web JavaScript syntax" {
                $files = rg --files server/static/js -g "*.js"
                foreach ($file in $files) {
                    node --check $file
                    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                }
            }
        } else {
            Write-Host "[SKIP] Web JavaScript syntax: node not found" -ForegroundColor Yellow
        }

        Invoke-Step "Android JVM tests" {
            Push-Location AideLink-app
            try { .\gradlew.bat testDebugUnitTest --no-daemon }
            finally { Pop-Location }
        }
    }

    if ($Tier -eq "full") {
        Invoke-Step "Android debug build" {
            Push-Location AideLink-app
            try { .\gradlew.bat assembleDebug --no-daemon }
            finally { Pop-Location }
        }
    }

    Write-Host "[PASS] AideLink $Tier test tier" -ForegroundColor Green
} finally {
    Pop-Location
}
