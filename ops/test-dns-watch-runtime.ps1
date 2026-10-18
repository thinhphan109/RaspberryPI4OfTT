# Exercise one real worker iteration with OS/SSH boundaries mocked, never live DNS.
$ErrorActionPreference='Stop'
$source=Get-Content (Join-Path $PSScriptRoot 'dns-watch.ps1') -Raw
$source=$source.Replace("Assert-Admin`r`nif(","if(").Replace("Assert-Admin`nif(","if(")
$source=$source.Replace(". (Join-Path `$PSScriptRoot 'dns-watch-policy.ps1')",'')
$source=$source.Replace(". (Join-Path `$PSScriptRoot 'pi-target.ps1')",'')
$source=$source.Replace('Start-Sleep -Seconds 30','break')
$source=$source.Replace('Local\PiControlDNS-','Local\PiControlDNSTest-')
. (Join-Path $PSScriptRoot 'dns-watch-policy.ps1')
$savedLocal=$env:LOCALAPPDATA
$testDir=Join-Path $env:TEMP ('PiControlDNS-test-'+[guid]::NewGuid())
$env:LOCALAPPDATA=$testDir
New-Item -ItemType Directory -Path (Join-Path $testDir 'PiControl') -Force|Out-Null
$guid='130ab74b-6c83-4ee4-9500-8776a3c2012e'
function Get-NetAdapter {return @{InterfaceGuid=$guid;ifIndex=7;Status='Up'}}
function Get-DnsClientServerAddress {return @{ServerAddresses=$script:servers}}
function Get-PiConnection {if(!$script:healthy){throw 'Pi offline'};return @{Address='192.168.10.20'}}
function Resolve-DnsName {return @{IPAddress='93.184.215.14'}}
function Get-ItemProperty {return @{NameServer=$script:static}}
function Clear-DnsClientCache {}
function Set-DnsClientServerAddress {
 param($InterfaceIndex,$ServerAddresses,[switch]$ResetServerAddresses)
 $script:changes++
 if($ResetServerAddresses){$script:servers=@('192.168.10.1');$script:static=''}else{$script:servers=@($ServerAddresses);$script:static=$ServerAddresses}
}
function Run-Case($name,$state,$servers,$healthy,$expectedStatus,$expectedChanges){
 $script:servers=$servers;$script:healthy=$healthy;$script:changes=0;$script:static=($servers -join ',')
 $path=Join-Path $testDir 'PiControl/dns-watch.json'
 $state|ConvertTo-Json|Set-Content $path
 & ([scriptblock]::Create($source)) -Action Watch
 $result=Get-Content $path -Raw|ConvertFrom-Json
 if($result.Status -ne $expectedStatus -or $script:changes -ne $expectedChanges){throw "$name failed: $($result|ConvertTo-Json -Compress), changes=$script:changes"}
}
function State($owned,$failures=0){return @{Enabled=$true;Status='Healthy';InterfaceGuid=$guid;OriginalNameServer='';OwnedAddress=$owned;Failures=$failures;Suspended=$false;PiAddress='192.168.0.106';Baseline=@();Detail=''}}
try{
 Run-Case 'Roaming updates verified Pi DNS' (State '192.168.0.106') @('192.168.0.106') $true 'Apply' 1
 Run-Case 'Transient failure leaves DNS alone' (State '192.168.0.106' 1) @('192.168.0.106') $false 'Waiting' 0
 Run-Case 'Third failure restores DHCP' (State '192.168.0.106' 2) @('192.168.0.106') $false 'Fallback' 1
 Run-Case 'Pi return restores filtering' (State '') @('192.168.10.1') $true 'Apply' 1
 Run-Case 'External DNS override pauses worker' (State '192.168.0.106') @('9.9.9.9') $true 'ExternalChange' 0
 Write-Output 'DNS watcher: 5 runtime scenarios PASS (OS/SSH mocked)'
}finally{
 $env:LOCALAPPDATA=$savedLocal
 $resolved=[IO.Path]::GetFullPath($testDir)
 if($resolved.StartsWith([IO.Path]::GetFullPath($env:TEMP)) -and (Split-Path $resolved -Leaf) -like 'PiControlDNS-test-*'){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
