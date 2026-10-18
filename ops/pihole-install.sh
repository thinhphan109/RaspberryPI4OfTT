#!/usr/bin/env bash
# First installation only. Run through pihole.ps1 after reviewing the upstream installer.
set -Eeuo pipefail
test "$(id -u)" = 0
test "$(hostname)" = raspberrypi
test "$(uname -m)" = aarch64
cd -- "$(dirname -- "$0")"
sha256sum -c installer.sha256
test ! -e /etc/pihole
test ! -e /etc/.pihole
test ! -e /var/www/html/admin
test ! -e /usr/bin/pihole-FTL
ip -4 address show dev wlan0 | grep -q '192.168.0.106/24'
if ss -H -lntu | awk '{print $5}' | grep -Eq ':(53|18853)$'; then
  echo 'Required port is already occupied'; exit 1
fi
if systemctl is-active --quiet systemd-resolved; then
  echo 'Resolved is active; re-audit before installing'; exit 1
fi
snapshot="/var/lib/pihole-trial/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$snapshot"
dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$snapshot/packages-before.tsv"
systemctl list-unit-files > "$snapshot/units-before.txt"
sha256sum /etc/resolv.conf > "$snapshot/resolv-before.sha256"
tar -czf "$snapshot/network-before.tar.gz" /etc/NetworkManager /etc/resolv.conf /etc/systemd/system/piwifi* 2>/dev/null
cp installer.sh installer.sha256 "$snapshot/"
cat > "$snapshot/disable.sh" <<'EOF'
#!/bin/sh
set -eu
systemctl disable --now pihole-FTL.service
echo 'Pi-hole stopped and disabled. Restore Windows DNS to automatic if configured.'
echo 'Installed packages and configuration retained for inspection; no shared package removal.'
EOF
chmod 700 "$snapshot/disable.sh"
on_failure() { systemctl stop pihole-FTL.service 2>/dev/null || true; echo "Installation failed; inspect root-only $snapshot/install.log"; }
trap on_failure ERR
install -d -m 755 /etc/pihole
cat > /etc/pihole/pihole.toml <<'EOF'
[dns]
upstreams = ["1.1.1.1", "1.0.0.1"]
queryLogging = false
listeningMode = "NONE"
[dhcp]
active = false
[ntp.ipv4]
active = false
[ntp.ipv6]
active = false
[ntp.sync]
active = false
[database]
DBimport = false
maxDBdays = 0
[database.network]
parseARPcache = false
[webserver]
port = "192.168.0.106:18853,127.0.0.1:18853"
acl = "+127.0.0.1,+192.168.0.101"
[webserver.session]
restore = false
[files]
database = "/run/pihole-trial/queries.db"
[misc]
dnsmasq_lines = ["bind-dynamic", "listen-address=127.0.0.1,192.168.0.106"]
EOF
chmod 640 /etc/pihole/pihole.toml
install -d -m 755 /etc/systemd/system/pihole-FTL.service.d
cat > /etc/systemd/system/pihole-FTL.service.d/trial.conf <<'EOF'
[Service]
RuntimeDirectory=pihole-trial
RuntimeDirectoryMode=0750
EOF
# FTL will need its RAM directory both now and after reboot.
cat > /etc/tmpfiles.d/pihole-trial.conf <<'EOF'
d /run/pihole-trial 0750 pihole pihole -
EOF
# User is created by upstream before FTL starts. The database is disabled; create
# its directory after installation as well, before the final controlled restart.
export DEBIAN_FRONTEND=noninteractive
bash ./installer.sh --unattended > "$snapshot/install.log" 2>&1
systemctl stop pihole-FTL
systemd-tmpfiles --create /etc/tmpfiles.d/pihole-trial.conf
python3 -B - <<'PY'
import pathlib, secrets, subprocess, pwd, os
account = pwd.getpwnam('thinh')
directory = pathlib.Path(account.pw_dir) / '.config/pihole-trial'
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chown(directory, account.pw_uid, account.pw_gid)
password = secrets.token_urlsafe(24)
path = directory / 'admin-password'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(password + '\n')
os.chown(path, account.pw_uid, account.pw_gid)
subprocess.run(['/usr/local/bin/pihole', 'setpassword', password], check=True, stdout=subprocess.DEVNULL)
PY
systemctl restart pihole-FTL
systemctl is-active --quiet pihole-FTL piwifi-web piwifi-observer NetworkManager ssh
sha256sum -c "$snapshot/resolv-before.sha256"
curl --noproxy '*' --max-time 10 --retry 3 --retry-connrefused --fail --silent --output /dev/null http://127.0.0.1:18853/admin/
curl --noproxy '*' --max-time 10 --fail --silent --output /dev/null http://127.0.0.1:18765/login
dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$snapshot/packages-after.tsv"
echo "Pi-hole installation complete. Snapshot: $snapshot"
pihole version
echo 'Admin password saved to ~/.config/pihole-trial/admin-password on Pi; not printed.'
