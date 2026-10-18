#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./scripts/uninstall.sh"
  exit 1
fi

systemctl disable --now piwifi-web 2>/dev/null || true
systemctl disable --now piwifi-observer 2>/dev/null || true
rm -f /etc/systemd/system/piwifi-observer.service
systemctl disable --now piwifi-guard.timer 2>/dev/null || true
systemctl stop piwifi-guard.service 2>/dev/null || true
systemctl stop piwifi-recover.timer piwifi-recover.service 2>/dev/null || true
rm -f /etc/systemd/system/piwifi-web.service
rm -f /etc/sudoers.d/piwifi-web
rm -f /usr/local/sbin/piwifi-helper
rm -f /usr/local/sbin/piwifi-guard /etc/systemd/system/piwifi-guard.service /etc/systemd/system/piwifi-guard.timer
rm -f /run/piwifi-guard.json
systemctl daemon-reload

echo "Application files in /opt/piwifi-web and /etc/piwifi-web.env were intentionally kept."
echo "Remove them manually only if you no longer need configuration/data."
echo "History in /var/lib/piwifi-observer and events in /var/lib/piwifi-events were kept."
