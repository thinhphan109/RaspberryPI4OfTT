$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'dns-watch-policy.ps1')
function Assert-Decision($expected,$arguments){
    $actual=Get-DnsWatchDecision @arguments
    if($actual -ne $expected){throw "Expected $expected, received $actual"}
}
Assert-Decision 'Apply' @{Healthy=$true;Failures=0;Current=@('192.168.0.1');PiAddress='192.168.0.106'}
Assert-Decision 'Healthy' @{Healthy=$true;Failures=0;Current=@('192.168.0.106');PiAddress='192.168.0.106';OwnedAddress='192.168.0.106'}
Assert-Decision 'Apply' @{Healthy=$true;Failures=0;Current=@('192.168.0.106');PiAddress='192.168.10.20';OwnedAddress='192.168.0.106'}
Assert-Decision 'Waiting' @{Healthy=$false;Failures=2;Current=@('192.168.0.106');OwnedAddress='192.168.0.106'}
Assert-Decision 'Fallback' @{Healthy=$false;Failures=3;Current=@('192.168.0.106');OwnedAddress='192.168.0.106'}
Assert-Decision 'Waiting' @{Healthy=$false;Failures=3;Current=@('192.168.0.1')}
Assert-Decision 'ExternalChange' @{Healthy=$true;Current=@('8.8.8.8');PiAddress='192.168.0.106';OwnedAddress='192.168.0.106'}
Assert-Decision 'ExternalChange' @{Healthy=$true;Current=@('192.168.0.106','8.8.8.8');PiAddress='192.168.0.106';OwnedAddress='192.168.0.106'}
Assert-Decision 'Paused' @{Healthy=$true;Current=@('8.8.8.8');PiAddress='192.168.0.106';Suspended=$true}
Assert-Decision 'ExternalChange' @{Healthy=$true;Current=@('9.9.9.9');PiAddress='192.168.0.106';Baseline=@('192.168.0.1')}
Assert-Decision 'Apply' @{Healthy=$true;Current=@('192.168.0.1');PiAddress='192.168.0.106';Baseline=@('192.168.0.1')}
Write-Output 'DNS watcher: 11 policy scenarios PASS'
