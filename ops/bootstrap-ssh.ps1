# Run interactively in the user's terminal. The password stays in OpenSSH.
param(
    [switch]$DryRun,
    [ValidatePattern('^[0-9.]+$')][string]$Address
)
$ErrorActionPreference = 'Stop'
$sshOptions = @('-o','StrictHostKeyChecking=yes')
if ($Address) {
    $parsedAddress = [System.Net.IPAddress]::Parse($Address)
    if ($parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'An IPv4 address is required.' }
    $sshOptions += @('-o',"HostName=$Address",'-o','HostKeyAlias=raspberrypi.local')
}
$keyPath = Join-Path $env:USERPROFILE '.ssh/rasp_tt_ed25519.pub'
if (-not (Test-Path -LiteralPath $keyPath)) { throw 'Dedicated public key is missing.' }
$publicKey = [IO.File]::ReadAllText($keyPath).Trim()
if ($publicKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?$') { throw 'Unexpected public key format.' }
$keyEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($publicKey))
$remoteScript = @'
set -eu
umask 077
mkdir -p "$HOME/.ssh"
file="$HOME/.ssh/authorized_keys"
if [ -L "$file" ]; then echo 'Refusing symlink authorized_keys' >&2; exit 1; fi
touch "$file"
key=$(printf %s __PUBLIC_KEY_BASE64__ | base64 -d)
if ! grep -qxF -- "$key" "$file"; then
    # A leading newline also handles an existing file without a trailing newline.
    printf '\n%s\n' "$key" >> "$file"
fi
chmod 700 "$HOME/.ssh"
chmod 600 "$file"
grep -qxF -- "$key" "$file"
echo 'Dedicated public key installed.'
'@
$remoteScript = $remoteScript.Replace('__PUBLIC_KEY_BASE64__',$keyEncoded).Replace("`r`n","`n")
$scriptEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
# This outer command has no quotes, variables or whitespace-bearing data.
# Windows PowerShell 5.1 native argument handling cannot strip the inner quotes.
$remoteCommand = "printf %s $scriptEncoded | base64 -d | sh"
if ($DryRun) { Write-Output $remoteCommand; return }
& ssh @sshOptions -o PubkeyAuthentication=no -o PreferredAuthentications=keyboard-interactive,password rasp-tt $remoteCommand
if ($LASTEXITCODE -ne 0) { throw 'Public key installation failed.' }
& ssh @sshOptions -o BatchMode=yes -o ConnectTimeout=10 rasp-tt 'hostname; id; uname -m'
if ($LASTEXITCODE -ne 0) { throw 'Public key installed but key authentication failed.' }
Write-Output 'SSH key authentication verified.'
if ($Address) { & (Join-Path $PSScriptRoot 'pi.ps1') -Action Check -Address $Address }
else { & (Join-Path $PSScriptRoot 'pi.ps1') -Action Check }
