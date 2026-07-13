Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
    Write-Output "Name: $($_.Name)"
    Write-Output "MAC:  $($_.MacAddress)"
    Write-Output "Speed: $($_.LinkSpeed)"
    Write-Output "---"
}

Write-Output "=== Wake-on-LAN Support ==="
Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
    $adapter = $_.Name
    try {
        $wol = Get-NetAdapterAdvancedProperty -Name $adapter -RegistryKeyword "*WakeOnMagicPacket" -ErrorAction SilentlyContinue
        if ($wol) {
            Write-Output "$adapter : WoL = $($wol.DisplayValue)"
        } else {
            Write-Output "$adapter : WoL not found in advanced properties"
        }
    } catch {
        Write-Output "$adapter : check failed - $_"
    }
}
