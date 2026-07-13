$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $p = $conn.OwningProcess
    Write-Output "Flask PID: $p"
    Get-Process -Id $p | Select-Object Id, ProcessName, StartTime | Format-List
} else {
    Write-Output "Port 5000 not listening"
}

Write-Output "---"
try {
    $r = Invoke-WebRequest -Uri http://localhost:5000/ping -UseBasicParsing -TimeoutSec 5
    Write-Output "Ping Status: $($r.StatusCode)"
    Write-Output "Ping Body: $($r.Content)"
} catch {
    Write-Output "Ping Error: $_"
}
