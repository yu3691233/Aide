try {
    $r = Invoke-WebRequest -Uri http://localhost:5000/ping -UseBasicParsing -TimeoutSec 5
    Write-Output "Ping: $($r.StatusCode) - $($r.Content)"
} catch {
    Write-Output "Ping Error: $_"
}
