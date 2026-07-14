$ErrorActionPreference = 'Stop'
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/devspace/start' -Method Post -TimeoutSec 15
if (-not $response.success) {
    $message = if ($response.message) { $response.message } else { 'DevSpace 启动失败' }
    throw $message
}
