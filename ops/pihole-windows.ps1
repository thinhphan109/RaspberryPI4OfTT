param([ValidateSet('Test','Enable','Update','Restore')][string]$Action='Test',[string]$Address)
# Compatibility entrypoint; preserves the original DNS backup from the Pi-hole trial.
& (Join-Path $PSScriptRoot 'dns-windows.ps1') -Action $Action -Address $Address