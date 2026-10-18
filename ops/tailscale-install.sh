#!/usr/bin/env bash
set -Eeuo pipefail
test "$(id -u)" = 0
test "$(hostname)" = raspberrypi
test "$(uname -m)" = aarch64
test ! -e /usr/bin/tailscale
test ! -e /etc/apt/sources.list.d/tailscale.list
snapshot="/var/lib/tailscale-setup/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$snapshot"
dpkg-query -W > "$snapshot/packages-before.tsv"
cp -a /etc/resolv.conf "$snapshot/resolv.conf"
sha256sum /etc/resolv.conf > "$snapshot/resolv.sha256"
tar -czf "$snapshot/network-before.tar.gz" /etc/NetworkManager /etc/systemd/system/piwifi* 2>/dev/null
cp -a /etc/pihole/pihole.toml "$snapshot/pihole.toml"
curl --fail --location --max-time 60 https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg -o "$snapshot/tailscale.gpg"
curl --fail --location --max-time 60 https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list -o "$snapshot/tailscale.list"
grep -q 'signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg' "$snapshot/tailscale.list"
install -m 644 "$snapshot/tailscale.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
install -m 644 "$snapshot/tailscale.list" /etc/apt/sources.list.d/tailscale.list
apt-get update > "$snapshot/apt-update.log" 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tailscale > "$snapshot/apt-install.log" 2>&1
systemctl enable --now tailscaled
tailscale set --accept-dns=false
sha256sum -c "$snapshot/resolv.sha256"
dpkg-query -W > "$snapshot/packages-after.tsv"
echo "Snapshot: $snapshot"
tailscale version
systemctl is-active tailscaled pihole-FTL piwifi-web piwifi-observer cloudflared
