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
        $files = @('ops/deploy.sh','pi-control/camera.py','pi-control/camera_agent.py','pi-control/camera_policy.py','pi-control/static/camera.js','pi-control/static/camera.css','pi-control/templates/camera.html','pi-control/systemd/pi-camera.service','pi-control/media.py','pi-control/media_agent.py','pi-control/media_policy.py','pi-control/media_extras.py','pi-control/media_catalog.py','pi-control/youtube_quality.py','pi-control/spotify_player.py','pi-control/native_player.py','pi-control/audio_control.py','pi-control/storage_writes.py','pi-control/static/audio.js','pi-control/static/storage-writes.js','pi-control/static/media.js','pi-control/static/quick-audio.js','pi-control/static/media-library.js','pi-control/systemd/pi-media.service','pi-control/systemd/pi-media-browser.service','pi-control/app.py','pi-control/robotvision.py','pi-control/read_cache.py','pi-control/runtime_config.py','pi-control/audio_agent.py','pi-control/audio_client.py','pi-control/camera_renderer.py','pi-control/render_jobs.py','pi-control/service_catalog.py','pi-control/service_catalog.json','pi-control/deployment_history.py','pi-control/hub.py','pi-control/apps.json','pi-control/static/hub.js','pi-control/helper/piwifi-dns-sync','pi-control/systemd/90-piwifi-dns','pi-control/templates/index.html',
            'pi-control/observer.py','pi-control/system_events.py','pi-control/state.py','pi-control/mcp_server.py',
            'pi-control/hardware.py','pi-control/security.py','pi-control/static/hardware.js',
            'pi-control/static/fonts/jetbrains-mono.woff2','pi-control/static/fonts/JetBrainsMono-OFL.txt',
            'pi-control/static/operations.js','pi-control/systemd/piwifi-observer.service',
            'pi-control/metrics.py','pi-control/helper/piwifi-guard',
            'pi-control/templates/help.html','pi-control/templates/mobile.html','pi-control/static/mobile.js','pi-control/static/native-player.js','pi-control/static/mobile.css','pi-control/static/interface.js','pi-control/static/service-help.js','pi-control/static/dashboard.css','pi-control/static/studio.css','pi-control/static/charts.js','pi-control/static/dashboard.js','pi-control/static/theme.js',
            'pi-control/static/raspberry-pi.png','pi-control/static/fonts/noto-sans.woff2','pi-control/static/fonts/OFL.txt',
            'pi-control/systemd/piwifi-guard.service','pi-control/systemd/piwifi-guard.timer',
            'pi-control/helper/piwifi-helper','pi-control/systemd/piwifi-web.service',
            'pi-control/sudoers/piwifi-web','pi-control/scripts/install.sh')
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
