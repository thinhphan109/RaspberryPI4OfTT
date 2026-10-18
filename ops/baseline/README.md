# Live source baseline — 2026-10-12

Downloaded over verified SSH from thinh@raspberrypi.local (192.168.1.30), Debian 13.7, aarch64. This is a reference snapshot, not part of the deployment payload; contains no runtime env or NetworkManager secret files.

- app.py: `/opt/piwifi-web/app.py`
- templates/index.html: `/opt/piwifi-web/templates/index.html`
- piwifi-helper: `/usr/local/sbin/piwifi-helper`
- wifi-fallback-guard: `/usr/local/sbin/wifi-fallback-guard`
- piwifi-web.service: `/etc/systemd/system/piwifi-web.service`

Local source and live source differ. Local backend has additional cookie/CSRF checks; live UI is larger. Reconcile intentionally before deployment; do not blindly overwrite either version. ZIP/DOCX remain useful original source/document artifacts.

Live guard hardcodes one preferred home profile, keeps other active Wi-Fi connections, preserves hotspot while it observes associated/TCP clients, and attempts home reconnection after two empty checks. No scheduler was found in inspected systemd/system cron/user cron locations. After temporary sudo authentication, root reported no crontab and guard journal reported no entries. Do not assume this guard runs automatically; do not enable it over the sole Wi-Fi management connection without recovery planning.

Web service is enabled/running; `/login` returns HTTP 200. Wi-Fi connection is active, Ethernet down. Pi root filesystem is 13% used (about 49 GB available). Noninteractive general sudo fails; only piwifi-helper is explicitly NOPASSWD. Root deployment/cleanup has not been run.
