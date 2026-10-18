param([ValidateSet('Install','Disable','Watch','Status')][string]$Action='Status')
$ErrorActionPreference='Stop'
$taskName='PiControl-DNS-'+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$stateDir=Join-Path $env:LOCALAPPDATA 'PiControl'
$statePath=Join-Path $stateDir 'dns-watch.json'
$installDir=Join-Path $env:ProgramFiles 'PiControlDNS'
. (Join-Path $PSScriptRoot 'dns-watch-policy.ps1')
function Read-State {
    if(Test-Path -LiteralPath $statePath){return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json}
    return $null
}
function Save-State($value){
    $json=$value|ConvertTo-Json
    if(!(Test-Path -LiteralPath $statePath) -or (Get-Content -LiteralPath $statePath -Raw).Trim() -ne $json.Trim()){
        New-Item -ItemType Directory -Force -Path $stateDir|Out-Null
        $temp=$statePath+'.tmp';[IO.File]::WriteAllText($temp,$json,[Text.UTF8Encoding]::new($false));Move-Item -LiteralPath $temp -Destination $statePath -Force
    }
}
function Assert-Admin {
    $p=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(!$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator is required to manage automatic Windows DNS.'}
}
if($Action -eq 'Status'){
    $state=Read-State
    if(!$state){Write-Output 'Automatic DNS is not enabled.'}else{$state|Format-List}
    exit
}
Assert-Admin
if($Action -eq 'Install'){
    # Fixed immutable task payload; never execute elevated code from a writable user directory.
    $existing=Read-State
    if($existing -and $existing.Enabled){& (Join-Path $PSScriptRoot 'dns-watch.ps1') -Action Disable}
    New-Item -ItemType Directory -Force -Path $installDir|Out-Null
    foreach($file in @('dns-watch.ps1','dns-watch-policy.ps1','dns-windows.ps1','pi-target.ps1')){
        if((Join-Path $PSScriptRoot $file) -ne (Join-Path $installDir $file)){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $installDir $file) -Force}
    }
    $adapter=Get-NetAdapter -Name WiFi
    $guid=[guid]$adapter.InterfaceGuid
    $key='HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\'+$guid.ToString('B')
    $original=(Get-ItemProperty -LiteralPath $key -Name NameServer -ErrorAction SilentlyContinue).NameServer
    # If manual Pi Control already set this Pi, preserve the pre-trial backup.
    $legacy=Join-Path $env:LOCALAPPDATA 'PiHoleTrial/wifi-dns-before.json'
    $cache=Join-Path $stateDir 'connection.json'
    if((Test-Path $legacy) -and (Test-Path $cache)){
        $before=Get-Content $legacy -Raw|ConvertFrom-Json
        $cached=Get-Content $cache -Raw|ConvertFrom-Json
        if([guid]$before.InterfaceGuid -eq $guid -and $original -eq $cached.Address){$original=[string]$before.NameServer}
    }
    Save-State @{Enabled=$true;Status='Starting';InterfaceGuid=$guid.ToString();OriginalNameServer=[string]$original;OwnedAddress='';Failures=0;Suspended=$false;PiAddress='';Baseline=@();Detail='Waiting for verified Pi and DNS probe.'}
    $user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    $taskAction=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "'+(Join-Path $installDir 'dns-watch.ps1')+'" -Action Watch')
    $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
    $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Pi Control: verified LAN DNS, three-failure DHCP fallback; per-user opt-in.' -Force|Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-Output 'Automatic DNS enabled. It also starts at sign-in. Close this window safely.'
    exit
}
if($Action -eq 'Disable'){
    $state=Read-State
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    if($state){
        $adapter=Get-NetAdapter -Name WiFi
        $current=@((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4).ServerAddresses)
        if([guid]$adapter.InterfaceGuid -eq [guid]$state.InterfaceGuid -and $state.OwnedAddress -and $current.Count -eq 1 -and $current[0] -eq $state.OwnedAddress){
            if([string]::IsNullOrWhiteSpace($state.OriginalNameServer)){Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses}
            else{Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ($state.OriginalNameServer -split '[,;\s]+'|Where-Object{$_})}
            Clear-DnsClientCache
        }
        $state.Enabled=$false;$state.Status='Disabled';$state.OwnedAddress='';$state.Detail='Automatic DNS stopped; external DNS changes are preserved.';Save-State $state
    }
    Write-Output 'Automatic DNS disabled.';exit
}
. (Join-Path $PSScriptRoot 'pi-target.ps1')
$mutex=[Threading.Mutex]::new($false,('Local\PiControlDNS-'+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
if(!$mutex.WaitOne(0)){exit}
try {
 while($true){
    $state=Read-State
    if(!$state -or !$state.Enabled){break}
    try{
        $adapter=Get-NetAdapter -Name WiFi
        if([guid]$adapter.InterfaceGuid -ne [guid]$state.InterfaceGuid){throw 'WiFi adapter identity changed; no DNS changes made.'}
        $current=@((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4).ServerAddresses)
        $healthy=$false;$pi=$null
        try{
            if($adapter.Status -ne 'Up'){throw 'WiFi disconnected'}
            $pi=Get-PiConnection
            Resolve-DnsName example.com -Server $pi.Address -DnsOnly -NoHostsFile -QuickTimeout -ErrorAction Stop|Out-Null
            $healthy=$true;$state.Failures=0;$state.PiAddress=$pi.Address
        }catch{$state.Failures=[Math]::Min(3,([int]$state.Failures+1))}
        # DHCP can legitimately change across networks. Only treat a new static
        # override as external ownership after fallback, not a new DHCP lease.
        $registry='HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\'+([guid]$adapter.InterfaceGuid).ToString('B')
        $static=(Get-ItemProperty -LiteralPath $registry -Name NameServer -ErrorAction SilentlyContinue).NameServer
        $baseline=if(!$state.OwnedAddress -and ![string]::IsNullOrWhiteSpace($static)){$state.Baseline}else{@()}
        $decision=Get-DnsWatchDecision -Healthy $healthy -Failures $state.Failures -Current $current -PiAddress $state.PiAddress -OwnedAddress $state.OwnedAddress -Suspended $state.Suspended -Baseline $baseline
        switch($decision){
            'Apply' {Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses $state.PiAddress;$state.OwnedAddress=$state.PiAddress;Clear-DnsClientCache;$state.Detail='Verified Pi DNS applied.'}
            'Healthy' {$state.OwnedAddress=$state.PiAddress;$state.Detail='Verified Pi and DNS reachable.'}
            'Fallback' {Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses;$state.OwnedAddress='';$state.Baseline=@((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4).ServerAddresses);Clear-DnsClientCache;$state.Detail='Pi unavailable after three checks; DHCP DNS restored. Filtering paused.'}
            'ExternalChange' {$state.Suspended=$true;$state.OwnedAddress='';$state.Detail='DNS changed outside Pi Control. Paused; enable again to resume.'}
            'Paused' {$state.Detail='Paused after external DNS change; enable again to resume.'}
            default {$state.Detail='Searching for Pi; DNS unchanged.'}
        }
        $state.Status=$decision;Save-State $state
    }catch{$state.Status='Error';$state.Detail=$_.Exception.Message;Save-State $state}
    Start-Sleep -Seconds 30
 }
}finally{$mutex.ReleaseMutex();$mutex.Dispose()}
