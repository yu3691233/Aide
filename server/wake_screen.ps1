Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait('{SPACE}')
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait('{SPACE}')
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
