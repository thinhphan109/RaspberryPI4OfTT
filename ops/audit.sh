#!/usr/bin/env bash
set -u
printf '\n== Identity ==\n'
hostname; id; uname -m; cat /etc/os-release
printf '\n== Resources ==\n'
df -h /; free -h; uptime
printf '\n== Network (no secrets) ==\n'
ip -brief address
nmcli -f NAME,UUID,TYPE,DEVICE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show
printf '\n== Services and fallback candidates ==\n'
systemctl status piwifi-web --no-pager || true
systemctl list-unit-files --no-pager | grep -Ei 'wifi|fallback|hotspot|guard' || true
printf '\n== Owned paths ==\n'
ls -ld /opt/piwifi-web /usr/local/sbin/piwifi-helper /etc/piwifi-web.env /etc/sudoers.d/piwifi-web /var/lib/piwifi-deploy 2>/dev/null || true
printf '\n== Listening ports ==\n'
ss -ltn
printf '\n== Deployment privilege ==\n'
sudo -n -l
