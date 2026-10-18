param([ValidateSet('Test','Enable','Update','Restore')][string]$Action = 'Test', [string]$Address)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'pi-target.ps1')
$piAddress = if ($Action -ne 'Restore') { (Get-PiConnection -Address $Address).Address } else { $null }
$adapter = Get-NetAdapter -Name 'WiFi'
$adapterGuid = [guid]$adapter.InterfaceGuid
if ($Action -eq 'Test') {
    Resolve-DnsName example.com -Server $piAddress -DnsOnly -NoHostsFile
    Resolve-DnsName example.com -Server $piAddress -DnsOnly -NoHostsFile -TcpOnly
    Resolve-DnsName doubleclick.net -Server $piAddress -DnsOnly -NoHostsFile
    exit
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run PowerShell as Administrator for Enable or Restore. Test needs no elevation.'
}
$backupDir = Join-Path $env:LOCALAPPDATA 'PiHoleTrial'
$backupPath = Join-Path $backupDir 'wifi-dns-before.json'
if ($Action -in @('Enable','Update')) {
    if ($Action -eq 'Update' -and -not (Test-Path -LiteralPath $backupPath)) { throw 'No original DNS backup. Use Enable first.' }
    if ($Action -eq 'Update') {
        $saved = Get-Content -LiteralPath $backupPath -Raw | ConvertFrom-Json
        if ([guid]$saved.InterfaceGuid -ne $adapterGuid) { throw 'Adapter differs from original DNS backup.' }
    }
    if ($Action -eq 'Enable' -and (Test-Path -LiteralPath $backupPath)) { throw 'A DNS backup already exists; use Update to follow the new Pi IP, or Restore.' }
    # Prove the DNS service is reachable before touching Windows configuration.
    Resolve-DnsName example.com -Server $piAddress -DnsOnly -NoHostsFile -ErrorAction Stop | Out-Null
    $key = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\' + $adapterGuid.ToString('B')
    $previous = (Get-ItemProperty -LiteralPath $key -Name NameServer -ErrorAction SilentlyContinue).NameServer
    if ($Action -eq 'Enable') {
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        @{ InterfaceGuid = $adapterGuid.ToString(); NameServer = $previous } |
            ConvertTo-Json | Set-Content -LiteralPath $backupPath -Encoding UTF8
    }
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses $piAddress
    Clear-DnsClientCache
    Write-Output "WiFi DNS now uses $piAddress. Backup: $backupPath"
} else {
    $previous = Get-Content -LiteralPath $backupPath -Raw | ConvertFrom-Json
    if ([guid]$previous.InterfaceGuid -ne $adapterGuid) { throw 'Adapter identity differs from backup.' }
    if ([string]::IsNullOrWhiteSpace($previous.NameServer)) {
        Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses
    } else {
        $servers = $previous.NameServer -split '[,;\s]+' | Where-Object { $_ }
        Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses $servers
    }
    Clear-DnsClientCache
    Remove-Item -LiteralPath $backupPath
    Write-Output 'Previous WiFi DNS configuration restored.'
}
