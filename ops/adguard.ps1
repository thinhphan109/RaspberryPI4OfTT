param([ValidateSet('Status','CopyPassword')][string]$Action='Status',[string]$Address)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'pi-target.ps1')
$connection=Get-PiConnection -Address $Address
$sshArgs=$connection.SshOptions
if($Action -eq 'CopyPassword'){
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
}else{
    & ssh @sshArgs rasp-tt 'systemctl is-active adguardhome piwifi-web piwifi-observer; ss -lntup'
    if($LASTEXITCODE -ne 0){throw 'Status check failed.'}
}
