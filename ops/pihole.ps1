param([ValidateSet('Deploy','Status','Disable','CopyPassword')][string]$Action='Status',[string]$Address)
if($Action -in @('Deploy','Disable')){throw 'Pi-hole was retired. Use AdGuard Home through Pi Control.'}
& (Join-Path $PSScriptRoot 'adguard.ps1') -Action $Action -Address $Address