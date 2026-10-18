# AdGuard Home — 2026-10-15

AdGuard Home v0.107.79 replaces Pi-hole. DNS remains at the Pi's current LAN
address, TCP/UDP 53. At migration time this is `192.168.0.106`; devices already
using that DNS need no changes. Router administration is not required.

Open **Pi Control** from the Desktop shortcut or `Pi-Control.cmd`. Its buttons
find the Pi, apply/restore Windows DNS, open AdGuard Home and copy its password.
Reopen Pi Control if an old window still displays Pi-hole labels.

Admin: <http://192.168.0.106:18853/>. Username: `admin`. Copy the password using
Pi Control or `./ops/adguard.ps1 -Action CopyPassword`. Credentials stay in
`/home/thinh/.config/adguardhome/credentials.json` on the Pi; do not publish them.

On iPhone: Settings → Wi-Fi → ⓘ → Configure DNS → Manual. Keep only the Pi's
current LAN IP, then save. In the dashboard Apps page, run the DNS check from
that iPhone to verify a matching DNS request and blocking probe. Cellular data,
a different Wi-Fi, Private Relay or a VPN can use another DNS path. AdGuard Home
cannot reliably remove YouTube video ads in the native iPhone application.

When the Pi changes Wi-Fi, NetworkManager events update its DNS listen address.
Pi Control discovers the Pi and can update Windows DNS. Its automatic Windows
mode is described in [DNS-AUTOMATION.md](DNS-AUTOMATION.md). iPhone manual DNS still
needs updating when the Pi's LAN IP changes. The Apps page shows the detected
address; this mechanism does not make a LAN IP stable or remotely reachable.

Enabled lists: the imported StevenBlack list and AdGuard DNS filter. Enabled
Pi-hole custom exact/regex rules were imported. Upstream uses Cloudflare DoH,
with plain DNS bootstrap/fallback. DHCP is disabled. Query history is bounded
to 2,000 entries in RAM; statistics use `/run` tmpfs. Both are lost on restart.
Filter updates, configuration changes and other host services may still write
to storage. No Tailscale changes were made for this migration.

## Recovery and maintenance

Service: `adguardhome.service`; binary: `/opt/adguardhome/AdGuardHome`;
configuration: `/etc/adguardhome/AdGuardHome.yaml` (root only).
Use `./ops/pi.ps1 -Action Deploy` for dashboard/helper updates.
Normal dashboard rollback can restore AdGuard-era snapshots. Old Pi-hole-era
snapshots are rejected before service changes because that needs a full migration
rollback.

Full migration recovery is deliberately retained, root-only, at
`/var/lib/adguard-migration`: Pi-hole file inventory/archive, previous dashboard
source and `restore.sh`. Run that script with sudo only when intentionally
reverting the entire migration. It stops AdGuard and restores Pi-hole plus its
previous dashboard. Shared apt dependencies were retained; no autoremove ran.
Recovery archive retention is manual until the migration has been accepted.

Windows DNS restore retains the original backup under
`%LOCALAPPDATA%\PiHoleTrial\wifi-dns-before.json`; keeping this old directory
name preserves the pre-trial DNS settings. Use Pi Control's Restore DNS button
or `./ops/dns-windows.ps1 -Action Restore` in elevated PowerShell.
