param(
    [ValidateSet('Create','Verify','RestoreFiles','ExportKey','ImportKey','OpenFolder')][string]$Action='Create',
    [string]$Address,
    [string]$File,
    [string]$Destination
)
$ErrorActionPreference='Stop'
$folder=Join-Path $env:LOCALAPPDATA 'PiControl/backup'
if($Action -eq 'OpenFolder') { New-Item -ItemType Directory -Force -Path $folder|Out-Null; Start-Process explorer.exe -ArgumentList ('"'+$folder+'"'); exit }
$arguments=@((Join-Path $PSScriptRoot 'backup.py'))
switch($Action){
    'Create' {
        . (Join-Path $PSScriptRoot 'pi-target.ps1')
        $pi=Get-PiConnection -Address $Address
        $options=ConvertTo-Json -Compress -InputObject @($pi.SshOptions)
        $arguments+=@('create','--ssh-options-base64',[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($options)))
    }
    'Verify' {
        if(!$File){$latest=Get-ChildItem -LiteralPath $folder -Filter '*.picbackup'|Sort-Object Name -Descending|Select-Object -First 1;if(!$latest){throw 'No backup found'};$File=$latest.FullName}
        $arguments+='verify'
    }
    'RestoreFiles' {if(!$File -or !$Destination){throw 'Specify -File and a NEW -Destination folder'};$arguments+='restore-files'}
    'ExportKey' {if(!$File){throw 'Specify -File for encrypted recovery key'};$arguments+='export-key'}
    'ImportKey' {if(!$File){throw 'Specify -File for encrypted recovery key'};$arguments+='import-key'}
}
if($File){$arguments+=@('--file',$File)}
if($Destination){$arguments+=@('--destination',$Destination)}
& python @arguments
if($LASTEXITCODE -ne 0){throw 'Backup operation failed. Python needs ops/backup-requirements.txt; Create also needs temporary sudo. See ops/BACKUP.md.'}
