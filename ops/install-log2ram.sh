#!/bin/bash
# Install a reviewed, pinned upstream bundle. Only for a new installation.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with temporary sudo.'; exit 1; }
bundle="$(cd "$(dirname "$0")/vendor/log2ram" && pwd)"
command -v rsync >/dev/null
command -v logrotate >/dev/null
[[ -d /var/log && ! -L /var/log ]]
[[ $(findmnt -n -o FSTYPE -T /var/log) != tmpfs ]]
for path in /usr/local/bin/log2ram /etc/log2ram.conf /var/hdd.log /var/log.hdd /etc/systemd/system/log2ram.service /etc/systemd/system/log2ram-daily.service /etc/systemd/system/log2ram-daily.timer /etc/logrotate.d/log2ram; do
    [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing path requires review: $path"; exit 1; }
done
[[ $(du -sx --block-size=1 /var/log | cut -f1) -lt 67108864 ]] || { echo '/var/log exceeds 64MiB; review before installation.'; exit 1; }
backup="/var/lib/pi-ops/log2ram-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup"
cp "$bundle/UPSTREAM.txt" "$backup/"
systemd-analyze cat-config systemd/journald.conf >"$backup/journald-before.txt"
du -sx --block-size=1 /var/log >"$backup/log-size-before.txt"
cat >"$backup/restore.sh" <<'RESTORE'
#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]]
systemctl disable --now log2ram-daily.timer
systemctl stop log2ram-daily.service || true
systemctl stop log2ram.service
if mountpoint -q /var/log; then echo 'Unexpected /var/log mount remains; stop and inspect.'; exit 1; fi
systemctl disable log2ram.service
rm -f /usr/local/bin/log2ram /etc/log2ram.conf /etc/systemd/system/log2ram.service /etc/systemd/system/log2ram-daily.service /etc/systemd/system/log2ram-daily.timer /etc/logrotate.d/log2ram
systemctl daemon-reload
echo 'Removed log2ram; original disk logs retained. Reboot to reopen application log files on disk.'
RESTORE
chmod 700 "$backup/restore.sh"
bash -n "$bundle/log2ram"
install -m 755 "$bundle/log2ram" /usr/local/bin/log2ram
for unit in log2ram.service log2ram-daily.service log2ram-daily.timer; do
    install -m 644 "$bundle/$unit" "/etc/systemd/system/$unit"
done
install -m 644 "$bundle/log2ram.logrotate" /etc/logrotate.d/log2ram
cat >/etc/log2ram.conf <<'CONFIG'
# Pinned upstream log2ram; managed by G:/RaspberryPI4OfTT/ops.
# Capacity, not a permanent 128MiB allocation. Journald remains volatile.
SIZE=128M
USE_RSYNC=true
NOTIFICATION=false
PATH_DISK="/var/log"
JOURNALD_AWARE=true
ZL2R=false
COMP_ALG=lz4
LOG_DISK_SIZE=256M
CONFIG
systemctl daemon-reload
systemctl enable log2ram.service log2ram-daily.timer
systemd-analyze verify /etc/systemd/system/log2ram.service /etc/systemd/system/log2ram-daily.service /etc/systemd/system/log2ram-daily.timer
echo "Recovery: $backup/restore.sh"
echo 'Installed and enabled. Reboot required before claiming /var/log is protected.'
