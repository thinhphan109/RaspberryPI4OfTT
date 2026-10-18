param(
    [ValidateSet('Authorize','Check','Audit','Deploy','Rollback')][string]$Action = 'Check',
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9._-]*$')][string]$Target = 'rasp-tt',
    [ValidatePattern('^[0-9.]+$')][string]$Address,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sshOptions = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10')
if ($Address) {
    [void][System.Net.IPAddress]::Parse($Address)
    if ($Target -ne 'rasp-tt') { throw '-Address is restricted to rasp-tt with its verified raspberrypi.local host key.' }
    $sshOptions += @('-o',"HostName=$Address",'-o','HostKeyAlias=raspberrypi.local')
}
if ($DryRun -and $Action -notin @('Audit','Deploy')) { throw 'DryRun supports Audit and Deploy only.' }
function Invoke-Pi([string]$Command) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    & ssh @sshOptions $Target "printf %s $encoded | base64 -d | sh"
    if ($LASTEXITCODE -ne 0) { throw "SSH failed (exit $LASTEXITCODE)." }
}
if ($Action -eq 'Authorize') {
    $authorizeOptions = @('-t','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10')
    if ($Address) { $authorizeOptions += @('-o',"HostName=$Address",'-o','HostKeyAlias=raspberrypi.local') }
    & ssh @authorizeOptions $Target 'sudo -v'
    if ($LASTEXITCODE -ne 0) { throw 'Temporary sudo authentication failed.' }
    Invoke-Pi 'sudo -n true'
    Write-Output 'Temporary sudo authentication verified; no sudoers changes made.'
    exit
}
if ($Action -eq 'Check') {
    Invoke-Pi 'hostname; id; uname -m; cat /etc/os-release; command -v nmcli; if sudo -n -l; then :; else echo Noninteractive-sudo-unavailable; fi'
    exit
}
if ($Action -eq 'Rollback') {
    Invoke-Pi 'sudo -n /var/lib/piwifi-deploy/latest/restore.sh'
    exit
}
$stage = '/tmp/piwifi-ops-' + [guid]::NewGuid().ToString('N')
$localStage = Join-Path ([IO.Path]::GetTempPath()) ('piwifi-ops-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $localStage | Out-Null
$remoteCreated = $false
try {
    $files = @('ops/audit.sh')
    if ($Action -eq 'Deploy') {
        $files = @('ops/deploy.sh','piwifi-manager/media.py','piwifi-manager/media_agent.py','piwifi-manager/media_policy.py','piwifi-manager/audio_control.py','piwifi-manager/storage_writes.py','piwifi-manager/static/audio.js','piwifi-manager/static/storage-writes.js','piwifi-manager/static/media.js','piwifi-manager/systemd/pi-media.service','piwifi-manager/systemd/pi-media-browser.service','piwifi-manager/app.py','piwifi-manager/hub.py','piwifi-manager/apps.json','piwifi-manager/static/hub.js','piwifi-manager/helper/piwifi-dns-sync','piwifi-manager/systemd/90-piwifi-dns','piwifi-manager/templates/index.html',
            'piwifi-manager/observer.py','piwifi-manager/state.py','piwifi-manager/mcp_server.py',
            'piwifi-manager/hardware.py','piwifi-manager/security.py','piwifi-manager/static/hardware.js',
            'piwifi-manager/static/fonts/jetbrains-mono.woff2','piwifi-manager/static/fonts/JetBrainsMono-OFL.txt',
            'piwifi-manager/static/operations.js','piwifi-manager/systemd/piwifi-observer.service',
            'piwifi-manager/metrics.py','piwifi-manager/helper/piwifi-guard',
            'piwifi-manager/static/dashboard.css','piwifi-manager/static/studio.css','piwifi-manager/static/charts.js','piwifi-manager/static/dashboard.js','piwifi-manager/static/theme.js',
            'piwifi-manager/static/raspberry-pi.png','piwifi-manager/static/fonts/noto-sans.woff2','piwifi-manager/static/fonts/OFL.txt',
            'piwifi-manager/systemd/piwifi-guard.service','piwifi-manager/systemd/piwifi-guard.timer',
            'piwifi-manager/helper/piwifi-helper','piwifi-manager/systemd/piwifi-web.service',
            'piwifi-manager/sudoers/piwifi-web','piwifi-manager/scripts/install.sh')
    }
    # Package an explicit allowlist; never include runtime secrets or the whole workspace.
    foreach ($file in $files) {
        $dest = Join-Path $localStage $file
        New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
        if ([IO.Path]::GetExtension($file) -in @('.png','.ttf','.woff2')) {
            [IO.File]::Copy((Join-Path $root $file),$dest)
        } else {
            $content = [IO.File]::ReadAllText((Join-Path $root $file)).Replace("`r`n","`n")
            [IO.File]::WriteAllText($dest,$content,[Text.UTF8Encoding]::new($false))
        }
    }
    $archive = Join-Path $localStage 'payload.tar.gz'
    & tar -czf $archive -C $localStage @files
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
    if ($DryRun) {
        & tar -tzf $archive
        if ($LASTEXITCODE -ne 0) { throw 'Archive verification failed.' }
        Write-Output "Dry run: payload validated for $Target; no SSH or deployment executed."
        return
    }
    Invoke-Pi "umask 077; mkdir '$stage'"
    $remoteCreated = $true
    & scp @sshOptions $archive "${Target}:${stage}/payload.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
    $script = if ($Action -eq 'Audit') { 'audit.sh' } else { 'deploy.sh' }
    Invoke-Pi "tar -xzf '$stage/payload.tar.gz' -C '$stage' && cd '$stage' && bash 'ops/$script'"
} finally {
    # Both paths are generated under fixed staging roots, never user-selected paths.
    if ($remoteCreated) {
        try { Invoke-Pi "rm -rf -- '$stage'" } catch { Write-Warning "Remote staging cleanup failed: $stage" }
    }
    $resolved = [IO.Path]::GetFullPath($localStage)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolved.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf).StartsWith('piwifi-ops-')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
