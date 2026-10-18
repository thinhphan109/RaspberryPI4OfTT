#!/bin/sh
# Read-only inventory before installing log2ram. Run through verified Pi SSH.
set -eu
hostname
uname -m
cat /etc/os-release
df -h / /var/log
findmnt -T /var/log
free -h
printf '\nInstalled packages\n'
dpkg-query -W rsync logrotate log2ram 2>/dev/null || true
printf '\nLogging services\n'
systemctl is-active systemd-journald rsyslog log2ram || true
systemctl is-enabled log2ram log2ram-daily.timer || true
printf '\nEffective journald configuration\n'
systemd-analyze cat-config systemd/journald.conf
printf '\nRoot audit availability\n'
if sudo -n true 2>/dev/null; then
    sudo -n du -xsh /var/log
    sudo -n du -xh --max-depth=1 /var/log
    sudo -n journalctl --disk-usage
    sudo -n find /var/log -xdev -type f -size +16M -printf '%s %p\n'
    sudo -n ls -ld /var/hdd.log /var/log.hdd 2>/dev/null || true
else
    printf 'Temporary sudo authentication required for full log inventory.\n'
fi
