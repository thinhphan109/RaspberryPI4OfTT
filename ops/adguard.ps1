param([ValidateSet('Status','CopyPassword')][string]$Action='Status',[string]$Address)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'pi-target.ps1')
$connection=Get-PiConnection -Address $Address
$sshArgs=$connection.SshOptions
if($Action -eq 'CopyPassword'){
    $modular = & ssh @sshArgs rasp-tt 'test -f /etc/pi-control/runtime.json && printf modular'
    if($LASTEXITCODE -ne 0){throw 'Could not identify the Pi Control installation.'}
    if(([string]$modular).Trim() -eq 'modular'){
        $python = @'
from pathlib import Path
values=dict(line.split('=',1) for line in Path('/etc/pi-control/dashboard/auth.env').read_text().splitlines() if '=' in line)
print(values['PIWIFI_USER'])
print(values['PIWIFI_PASS'])
'@
        $payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($python))
        $result = & ssh @sshArgs rasp-tt "printf %s $payload | base64 -d | sudo -n python3 -B -"
        if($LASTEXITCODE -ne 0){throw 'Sudo authentication expired. Use Pi Control > Cấp quyền sudo tạm, then retry.'}
        if($result.Count -lt 2){throw 'Dashboard credentials were unavailable.'}
        $username=[string]$result[0];$password=[string]$result[1]
        Set-Clipboard -Value $password.Trim()
        $password=$null;$result=$null
        Write-Output ("Dashboard username: {0}. Password copied to clipboard." -f $username.Trim())
    }else{
        $python = @'
import json,pathlib
print(json.loads((pathlib.Path.home()/".config/adguardhome/credentials.json").read_text())["password"])
'@
        $payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($python))
        $encoded = & ssh @sshArgs rasp-tt "printf %s $payload | base64 -d | python3 -B"
        if($LASTEXITCODE -ne 0){throw 'Could not read AdGuard Home credentials.'}
        Set-Clipboard -Value ([string]$encoded).Trim()
        $encoded=$null
        Write-Output 'AdGuard Home username: admin. Password copied to clipboard.'
    }
}else{
    & ssh @sshArgs rasp-tt 'systemctl is-active adguardhome piwifi-web piwifi-observer; ss -lntup'
    if($LASTEXITCODE -ne 0){throw 'Status check failed.'}
}
