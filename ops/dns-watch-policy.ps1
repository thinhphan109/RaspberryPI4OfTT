# Pure policy: never mutate DNS owned by another configuration tool.
function Get-DnsWatchDecision {
    param([bool]$Healthy,[int]$Failures,[string[]]$Current,[string]$PiAddress,[string]$OwnedAddress,[bool]$Suspended,[string[]]$Baseline=@())
    if($Suspended){return 'Paused'}
    if($OwnedAddress -and (@($Current).Count -ne 1 -or $Current[0] -ne $OwnedAddress)){return 'ExternalChange'}
    if(!$OwnedAddress -and $Baseline.Count -and (($Current -join ',') -ne ($Baseline -join ','))){return 'ExternalChange'}
    if($Healthy){
        if(@($Current).Count -eq 1 -and $Current[0] -eq $PiAddress){return 'Healthy'}
        return 'Apply'
    }
    if($Failures -ge 3 -and $OwnedAddress){return 'Fallback'}
    return 'Waiting'
}
