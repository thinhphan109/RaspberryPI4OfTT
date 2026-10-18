# Pi-hole trial — 2026-10-15

Historical reference: Pi-hole has been replaced and removed. Use
[AdGuard Home](ADGUARD.md) for current operations. Old installer scripts are
historical and must not be used to redeploy Pi-hole over AdGuard Home.

Installed natively on the existing Debian 13 aarch64 Pi alongside its current
projects. Core v6.4.3 (`f47b8ed`), Web v6.6 (`b2a4078`), FTL v6.7.1.
No router access needed. Windows and Pi use the same Wi-Fi and can reach each other.

## Use

- DNS: `192.168.0.106`, TCP/UDP 53.
- Admin: <http://192.168.0.106:18853/admin/>. Initial admin ACL allows localhost
  and the tested Windows IP `192.168.0.101` only.
- `./ops/pihole.ps1 -Action CopyPassword` copies the generated password from the
  Pi into the Windows clipboard without printing it. Keep it in a password manager.
- `./ops/pihole-windows.ps1 -Action Test` tests DNS explicitly without changing
  the Windows DNS configuration.
- In an **Administrator PowerShell** at this workspace:
  `./ops/pihole-windows.ps1 -Action Enable` saves existing IPv4 WiFi DNS settings
  into `%LOCALAPPDATA%/PiHoleTrial/wifi-dns-before.json`, then sets this adapter's
  DNS to the Pi. VPN and other adapters are not changed.
- Restore with `./ops/pihole-windows.ps1 -Action Restore` in Administrator
  PowerShell. Restore Windows first, before disabling Pi-hole.
- Windows WiFi had no IPv6 DNS servers during the audit. Browser Secure DNS or
  VPN-provided DNS can bypass Pi-hole; account for those when judging blocking.

## Scope and coexistence

DHCP and Pi-hole NTP are disabled. Pi's own resolver remains unchanged. Dashboard
still uses 18765. DNS uses `listeningMode=NONE` plus explicit `bind-dynamic` and
`listen-address=127.0.0.1,192.168.0.106`; no wildcard DNS listener, no DNS listener
on fallback AP address 192.168.50.1. This avoids claiming the AP DNS endpoint.
Physical hotspot/client, outage and reboot behavior have not been tested.

The IP is a DHCP lease, not a reservation. We did not assign an arbitrary static
address on someone else's router. If the Pi changes IP or moves Wi-Fi, update
the explicit DNS listen-address, webserver.port and Windows DNS; if the Windows
IP changes, update webserver.acl through SSH. The helper scripts currently target
the verified `192.168.0.106` address and retain the known Pi host key.

## Disk and resource policy

Query logging off; long-term query database disabled (`maxDBdays=0`, no import);
database path under `/run/pihole-trial`, created by service RuntimeDirectory.
Session persistence and ARP table polling disabled. Existing `/var/log` log2ram
setup remains. Blocklists, configuration, package installs and scheduled list
updates still write persistently; this is not a claim of zero writes for Pi-hole
or the whole host. RAM history is lost on service restart or reboot.

## Installation and recovery

`pihole.ps1` is a dedicated first-install runner because dashboard Deploy/Rollback
does not cover third-party software. It uploads the reviewed official installer
from Windows TEMP, verifies SHA256 and runs it as an independent systemd job.
The upstream installer checks out its latest stable component tags. Snapshot
contains its installer SHA256 and version/package evidence; no automatic upgrades
were configured. Re-audit before any future repair or upgrade.

Root-only snapshot: `/var/lib/pihole-trial/20261015T050812Z/`. Includes the original
network configuration (secret-bearing, do not export), package inventory and
installer log. Keep this single initial recovery snapshot for the trial.
Generated admin secret is outside the workspace at
`/home/thinh/.config/pihole-trial/admin-password`, mode 0600.

Emergency stop: `./ops/pihole.ps1 -Action Disable`, or
`sudo systemctl disable --now pihole-FTL`. This retains files and dependencies;
do not blindly use the upstream uninstaller to remove shared packages.
The snapshot's `disable.sh` performs the same scoped stop.

First run installed correctly, but final localhost curl inherited root's proxy
and failed; the failure handler stopped FTL. Health probes were corrected with
`--noproxy '*'`, FTL restarted, and manual finalization completed. Installer
transient job's original failure is historical; final health evidence is separate.

Validation: direct Windows UDP/TCP DNS queries resolve example.com and block
doubleclick.net with 0.0.0.0 / ::. Admin login page HTTP 200; authenticated API login
and logout succeed; initial blocklist has 73,634 domains. Existing web, observer,
NetworkManager and SSH active. Pi resolver checksum unchanged. Windows system DNS
is not changed by installation or the Test action.

Windows follow-up: user ran Enable as Administrator successfully. Verified WiFi
DNS is now 192.168.0.106, no IPv6 DNS; default DNS queries resolve example.com
and block doubleclick.net to 0.0.0.0 / ::. HTTPS example.com returns HTTP 200.
Backup exists for Restore. Fixed PowerShell 5.1 InterfaceGuid string by explicitly
casting to [guid] before formatting the registry path and comparing identities.

60-second post-install light-load sample: FTL RSS 10,052 kB, average CPU 0.517%
of one core, process write_bytes delta 0. This short sample does not establish
behavior under heavy load or zero writes by the whole host. Full network/profile
and piwifi unit archive comparison passed after installation.
