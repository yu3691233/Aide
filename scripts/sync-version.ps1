param(
    [switch]$Commit
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$GradleFile = Join-Path $ProjectRoot "AideLink-app\app\build.gradle.kts"
$VersionJson = Join-Path $ProjectRoot "version.json"
$ServerVersionJson = Join-Path $ProjectRoot "server\version.json"

# Read versionName from build.gradle.kts
$gradle = Get-Content $GradleFile -Raw
$match = [regex]::Match($gradle, 'versionName\s*=\s*"([^"]+)"')
if (!$match.Success) {
    Write-Error "Cannot find versionName in build.gradle.kts"
    exit 1
}
$version = $match.Groups[1].Value
$now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")

# Sync both version.json files
$versionObj = @{ version = $version; updated_at = $now } | ConvertTo-Json
$versionObj | Set-Content $VersionJson -Encoding UTF8
$versionObj | Set-Content $ServerVersionJson -Encoding UTF8

Write-Output "Synced version to $version"

if ($Commit) {
    & git -C $ProjectRoot add $VersionJson $ServerVersionJson
    & git -C $ProjectRoot commit -m "v$version — sync version"
    Write-Output "Committed as v$version"
}
