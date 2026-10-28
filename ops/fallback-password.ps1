param([string]$Address)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'pi-target.ps1')
$connection=Get-PiConnection -Address $Address
$sshArgs=$connection.SshOptions
$python=@'
import json
from pathlib import Path
data=json.loads(Path('/etc/pi-control/network/fallback-access.json').read_text())
print(data['ssid'])
print(data['password'])
'@
$payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($python))
$script="printf %s $payload | base64 -d | sudo -n python3 -B -"
$encodedScript=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
$remoteCommand="printf %s $encodedScript | base64 -d | sh"
$result=& ssh @sshArgs rasp-tt $remoteCommand
if($LASTEXITCODE -ne 0){throw 'Sudo authentication expired. Use Pi Control > Cấp quyền sudo tạm, then retry.'}
if($result.Count -lt 2){throw 'Thông tin Wi-Fi dự phòng chưa có.'}
$ssid=[string]$result[0];$password=[string]$result[1]
Set-Clipboard -Value $password.Trim()
$password=$null;$result=$null
Write-Output ("SSID: {0}. Mật khẩu đã được chép vào clipboard." -f $ssid.Trim())
