# Raspberry Pi dashboard — 2026-10-12

The existing Flask/Gunicorn service now serves a responsive Vietnamese dashboard at port 18765. Existing login credentials remain in `/etc/piwifi-web.env`.

Read-only metrics: SoC temperature, sampled CPU percentage and session chart, CPU load, RAM available/used, swap, uptime, mounted block-device disk usage, and fixed service states. No extra metrics agent, database, CDN, external fonts or cloud service is needed. Polling every five seconds pauses when the browser tab is hidden. A lost connection marks displayed values stale. Disk usage is capacity monitoring, not SD-card SMART health. The chart is not persisted after closing the tab.

Network operations retain CSRF protection and require login. Root helper rejects profiles that are not Wi-Fi or are bound to a different interface. Connect schedules an independent systemd recovery check after 90 seconds when there is a previous connection. The check preserves the expected new profile if it has an IPv4 address; otherwise it attempts the previous profile. This is local connectivity validation, not proof of Internet availability.

`piwifi-guard.timer` starts 60 seconds after boot and runs again 30 seconds after each guard pass completes. Guard preserves every active connection, including AP, and does not roam away from a hotspot. With radio enabled and device disconnected it tries saved autoconnect infrastructure profiles by descending priority, within a two-minute attempt budget, then activates Pi-Fallback. Disabled/unavailable/busy radio is preserved. Errors go to systemd journal. AP return is manual via the dashboard.

This deployment did not change NetworkManager profiles. Pi-Fallback already existed on this Pi: RaspPI4OfTT, 192.168.50.1/24, shared IPv4, priority -50. Installer expects that profile to exist; provisioning another Pi requires creating and validating an AP profile first. Legacy unscheduled guard was retired after backup.

Validation: six unittest cases covering real Linux telemetry, authentication/CSRF, dashboard render, non-Wi-Fi rejection, successful/failed recovery decisions, AP preservation, multiple candidate networks, fallback activation and disabled-radio handling. Authenticated live HTTP/API checks pass; new units pass systemd-analyze verification; guard live pass preserves current connection. Layout reviewed at desktop and 390px mobile viewport without horizontal page overflow.

Physical tests pending: boot with known Wi-Fi unavailable, wrong Wi-Fi credentials, real AP-client persistence and recovery after a failed network switch. Arrange independent recovery/Ethernet before these tests; they were not simulated as completed physical tests.

Rollback: `ops/pi.ps1 -Action Rollback` restores the latest pre-deployment file/service snapshot. Secrets stay root-only. Application deployment does not roll back apt packages or NetworkManager profiles.
The original pre-dashboard snapshot is `/var/lib/piwifi-deploy/20261012T095557-7339`. Latest final-change snapshot: `/var/lib/piwifi-deploy/20261012T100025-8123` (earlier dashboard iteration). Both are retained for recovery; staging/test files were removed.
