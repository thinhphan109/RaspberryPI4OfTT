# Raspberry Pi operations

Encrypted off-Pi backup and GitHub checks: [BACKUP.md](BACKUP.md).

Daily launcher: open `Pi-Control.cmd` at workspace root or Desktop **Pi Control**.
Desktop audio processing: [EASYEFFECTS.md](EASYEFFECTS.md).
Dashboard devices/Bluetooth: [AUDIO-BLUETOOTH.md](AUDIO-BLUETOOTH.md).
Media resource controls and Pi sleep limitations: [RESOURCE-MODE.md](RESOURCE-MODE.md).
Persistent SD write statistics: `piwifi-manager/docs/V312_STORAGE_WRITES.md`.
Dashboard Media remote: [MEDIA.md](MEDIA.md).
Current DNS backend is AdGuard Home. Usage and migration recovery:
[ADGUARD.md](ADGUARD.md), `piwifi-manager/docs/V34_RELEASE.md`.
Dashboard app hub uses event-driven DNS IP sync.
Dashboard 3.5 device verification and Windows background DNS mode:
[DNS-AUTOMATION.md](DNS-AUTOMATION.md).

Tailscale installation and remaining client/DNS steps: [TAILSCALE.md](TAILSCALE.md).

Historical Pi-hole trial: [PIHOLE.md](PIHOLE.md). Pi-hole was removed on
2026-10-15; its root-only migration archive is retained on the Pi.

Host log buffering: see `ops/LOG2RAM.md`. Since 2026-10-14, `/var/log` is a
128 MiB log2ram tmpfs with daily 23:55 sync and clean-shutdown sync. Existing
journald remains volatile. Manual pinned upstream installation and root-only
recovery path are documented there; do not overwrite backing log directories.

Local entrypoint: `./ops/pi.ps1 -Action Check|Audit|Deploy|Rollback`.
Current atomic-release workflow: `piwifi-manager/docs/V31_RELEASE.md`. Installer must run through Deploy, not standalone. Managed app/helper/library symlinks are expected; snapshot/restore supports both legacy directories and releases. A brief service restart still occurs.
Use `-Action Authorize` interactively when root access is needed. Enter the sudo password directly in the terminal; this refreshes the existing temporary sudo timestamp and verifies noninteractive access. It makes no sudoers changes. Authorization expires according to the Pi's sudo configuration.
Default SSH alias: `rasp-tt`. An alternative configured alias can be supplied with `-Target`.
If mDNS fails, supply the Pi's confirmed IPv4 with `-Address`, for example `./ops/pi.ps1 -Action Check -Address 192.168.0.106`. This retains the verified `raspberrypi.local` host-key check and is restricted to `rasp-tt`.

Dashboard 3.2: `piwifi-manager/docs/V32_RELEASE.md`. New telemetry/history is RAM-only, survives closing the browser but not restarting observer/reboot. Legacy SQLite is preserved and is no longer the live history source. GPIO is read-only and fan control is skipped.
Use `-Action Deploy -DryRun` or `-Action Audit -DryRun` to validate packaging locally without connecting. No payload is left on disk.

## Connection setup

User confirmed `raspberrypi` / SSH user `thinh`, password login, no Ethernet. On 2026-10-12, `raspberrypi.local` resolved to `192.168.1.30`, SSH port 22 responded, and existing known_hosts entries for both names agreed. Run `./ops/bootstrap-ssh.ps1` interactively once to enter the SSH password directly into OpenSSH and install the dedicated public key. The script does not disable password login.

Use a dedicated Ed25519 key and add its public key to the Pi user's `~/.ssh/authorized_keys`.
Keep the private key outside this workspace. Add a concrete host to the Windows user's `.ssh/config`:

```sshconfig
Host rasp-tt
    HostName <confirmed Pi IP or hostname>
    User <confirmed SSH user>
    IdentityFile ~/.ssh/rasp_tt_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    ServerAliveInterval 15
    ServerAliveCountMax 3
```

Verify the host-key fingerprint against the Pi console or another trusted channel before registering it in `known_hosts`. Unlock an encrypted key using ssh-agent. The operations script uses noninteractive key authentication.

`Check` identifies the host and available sudo privileges. `Audit` reads network/service metadata without reading secret files. It does not modify the network. Audit output still contains private network names and should not be published.

`Deploy` uploads an explicit source allowlist, parses Python, snapshots existing application/helper/unit/sudoers/env, installs, restarts and checks `/login`. Deployment requires working noninteractive sudo; do not grant all sudo commands merely to make this script pass. Provision a narrower root deployment entrypoint after auditing the real Pi if needed.

Failure after snapshot triggers restoration. `Rollback` restores the latest snapshot, including its original running/enabled state. Snapshots contain secrets, are root-only and stay on the Pi. This rollback covers project files and service state; apt package installation is not reversed. NetworkManager profiles are not changed by this deployment.

Staging is removed automatically; a failed SSH connection can leave the exact printed remote staging directory for later cleanup. Backups are deliberately retained until the real system has been reviewed. Health verification checks web availability, not real Wi-Fi fallback behavior.

Do not run overlapping operations. Wi-Fi transitions require an independent recovery job on the Pi or an Ethernet/console recovery path. Neither SSH nor a VPN can recover a Pi with no reachable network.

Dashboard 3.0 operation/history/MCP details: `piwifi-manager/docs/V3_RELEASE.md`. Deploy snapshots observer unit, root helper library and release metadata; success keeps five snapshots. Observer history and root event history survive deployment/rollback. Read-only MCP `raspberry_pi` uses SSH stdio; restart this server in Codex after configuration changes.
