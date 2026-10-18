# Tailscale setup — 2026-10-15

Pi installed from official signed Debian trixie stable repository, version
1.104.1. Device `rasp-tt` authenticated, Tailscale IPv4 `100.66.23.14`,
MagicDNS `rasp-tt.tail0109ce.ts.net`. tailscaled enabled at boot.
Pi uses accept-dns=false to avoid a self-dependent DNS loop. No exit node,
subnet routes or Tailscale SSH enabled; existing OpenSSH remains available.
Cloudflare Tunnel and piwifi services remain active.

Pi-hole updated with recovery snapshot
`/var/lib/tailscale-setup/20261015T053158Z-pihole/restore.sh`.
DNS binds localhost, original LAN192.168.0.106 and Tailscale100.66.23.14 only,
using bind-dynamic. AP192.168.50.1 is not claimed. Admin listens on IPv4 port
18853 with ACL allowing localhost, original Windows192.168.0.101 and
100.64.0.0/10; Tailscale policy still governs actual remote access.
Query history remains RAM-only/disabled on disk as documented in PIHOLE.md.
Pi-local DNS queries over the Tailscale address resolve normal domains and block
doubleclick.net. Cross-device, reboot and physical Wi-Fi migration tests pending.

## Pending Windows connection

Windows has Tailscale1.98.2 but backend reports NoState, no Tailscale IP.
Agent cannot restart Windows service without elevation. In Administrator
PowerShell run:

```powershell
Restart-Service Tailscale
& 'C:\Program Files\Tailscale\tailscale.exe' login --accept-dns=false
```

Log in using the same account as Pi. Keep existing DNS until connectivity verified:

```powershell
tailscale status
tailscale ping 100.66.23.14
Resolve-DnsName example.com -Server 100.66.23.14
Resolve-DnsName doubleclick.net -Server 100.66.23.14
ssh -o HostName=100.66.23.14 -o HostKeyAlias=raspberrypi.local rasp-tt
```

## Pending tailnet DNS

At https://console.tailscale.com/admin/dns add custom global nameserver
100.66.23.14 then enable Override DNS servers. Pi keeps accept-dns=false.
On Windows set `tailscale set --accept-dns=true` only after verification.
In Administrator PowerShell restore original WiFi DNS with
`./ops/pihole-windows.ps1 -Action Restore` so WiFi is no longer tied to old LAN IP.
This is pending, not yet performed. Then test default DNS and blocking.

On iPhone install official Tailscale, log in to same account, allow VPN configuration
and connect with Tailscale DNS enabled. Restore per-WiFi manual DNS to Automatic.
No exit node needed. Test on cellular by opening the dashboard:
http://100.66.23.14:18765 and Pi-hole http://100.66.23.14:18853/admin/.
Pi must be online. Tailnet DNS choice affects devices that accept tailnet DNS.

Key expiry remains default; no security policy or expiry weakening performed.
Stop Tailscale with `sudo tailscale down` if required; do not stop it until DNS
clients are restored. Pi-hole snapshot restores previous listeners, not packages.
