#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run through ops/pi.ps1 -Action Deploy'; exit 1; }
[[ ! -f /etc/pi-control/runtime.json ]] || { echo 'Modular SSD system: use the SSD bootstrap installer'; exit 1; }
[[ ${PIWIFI_DEPLOY_LOCKED:-0} == 1 ]] || { echo 'Use the snapshot/lock deployment entrypoint'; exit 1; }
APP_USER="${SUDO_USER:-thinh}"
APP_GROUP="$(id -gn "$APP_USER")"
APP_DIR=/opt/piwifi-web
RELEASE_ROOT=/opt/piwifi-releases
release="$RELEASE_ROOT/$PIWIFI_RELEASE_ID"
cd "$(dirname "$0")/.."
python3 -c 'import flask' >/dev/null 2>&1 && command -v gunicorn >/dev/null && command -v openssl >/dev/null || { apt update; apt install -y python3-flask gunicorn openssl; }
command -v iw >/dev/null || { apt update; apt install -y iw; }
python3 -c 'import yaml' >/dev/null 2>&1 || { apt update; apt install -y python3-yaml; }
python3 -c 'import websocket' >/dev/null 2>&1 || { apt update; apt install -y python3-websocket; }
python3 -c 'from PIL import Image' >/dev/null 2>&1 && command -v ffmpeg >/dev/null || { apt update; apt install -y python3-pil ffmpeg; }
[[ ! -L "$RELEASE_ROOT" ]] || exit 1
install -d -o root -g root -m 0755 "$RELEASE_ROOT"
[[ ! -e "$release" ]] || { echo 'Release already exists'; exit 1; }
install -d -o root -g root -m 0755 "$release/templates" "$release/static/fonts" "$release/helper"
install -o root -g root -m 0644 app.py robotvision.py read_cache.py runtime_config.py audio_agent.py audio_client.py camera_renderer.py render_jobs.py service_catalog.py service_catalog.json deployment_history.py hub.py media.py media_agent.py media_policy.py media_extras.py media_catalog.py youtube_quality.py spotify_player.py native_player.py audio_control.py camera.py camera_agent.py camera_policy.py storage_writes.py system_events.py apps.json metrics.py observer.py state.py mcp_server.py hardware.py security.py "$release/"
install -o root -g root -m 0644 templates/index.html "$release/templates/"
install -o root -g root -m 0644 templates/camera.html templates/help.html templates/mobile.html "$release/templates/"
install -o root -g root -m 0644 templates/mini-display.html "$release/templates/"
install -o root -g root -m 0644 mini_display_store.py "$release/"
install -o root -g root -m 0644 static/mini-display.js static/mini-display.css static/mini-fallback-qr.svg "$release/static/"
install -d -o root -g root -m 0755 "$release/static/mini-cat"
install -o root -g root -m 0644 static/mini-cat/*.png "$release/static/mini-cat/"
install -o root -g root -m 0644 static/camera.js static/camera.css static/interface.js static/service-help.js static/mobile.js static/mobile.css static/native-player.js "$release/static/"
install -o root -g root -m 0644 static/dashboard.css static/studio.css static/charts.js static/dashboard.js static/hub.js static/media.js static/quick-audio.js static/media-library.js static/audio.js static/storage-writes.js static/operations.js static/hardware.js static/theme.js static/raspberry-pi.png "$release/static/"
install -o root -g root -m 0644 static/fonts/noto-sans.woff2 static/fonts/OFL.txt "$release/static/fonts/"
install -o root -g root -m 0644 static/fonts/jetbrains-mono.woff2 static/fonts/JetBrainsMono-OFL.txt "$release/static/fonts/"
install -o root -g root -m 0755 helper/piwifi-helper helper/piwifi-guard helper/piwifi-dns-sync "$release/helper/"
sed "s/^thinh /${APP_USER} /" sudoers/piwifi-web > "$release/sudoers"
visudo -cf "$release/sudoers"
for unit in piwifi-web piwifi-observer piwifi-guard; do
  sed -e "s/^User=thinh$/User=${APP_USER}/" -e "s/^Group=thinh$/Group=${APP_GROUP}/" "systemd/$unit.service" > "$release/$unit.service"
done
install -o root -g root -m 0644 systemd/piwifi-guard.timer "$release/piwifi-guard.timer"
install -o root -g root -m 0644 systemd/pi-media.service systemd/pi-media-browser.service systemd/pi-camera.service "$release/"
systemctl stop piwifi-guard.timer piwifi-guard.service piwifi-observer piwifi-web
if [[ -L "$APP_DIR" ]]; then
  previous="$(readlink -f "$APP_DIR")"
  [[ "$(dirname "$previous")" == "$RELEASE_ROOT" ]] || { echo 'Unexpected app symlink'; exit 1; }
elif [[ -d "$APP_DIR" ]]; then
  # First migration pauses services; later switches use atomic rename.
  mv -- "$APP_DIR" "$RELEASE_ROOT/legacy-$PIWIFI_RELEASE_ID"
elif [[ -e "$APP_DIR" ]]; then
  echo 'Unexpected application path'; exit 1
fi
ln -s "$release" "/opt/.piwifi-web-$PIWIFI_RELEASE_ID"
mv -Tf "/opt/.piwifi-web-$PIWIFI_RELEASE_ID" "$APP_DIR"
for name in piwifi-helper piwifi-guard; do
  ln -s "$APP_DIR/helper/$name" "/usr/local/sbin/.$name-$PIWIFI_RELEASE_ID"
  mv -Tf "/usr/local/sbin/.$name-$PIWIFI_RELEASE_ID" "/usr/local/sbin/$name"
done
if [[ -d /usr/local/lib/piwifi && ! -L /usr/local/lib/piwifi ]]; then
  rm -f /usr/local/lib/piwifi/state.py
  if [[ -d /usr/local/lib/piwifi/__pycache__ && ! -L /usr/local/lib/piwifi/__pycache__ ]]; then rm -rf /usr/local/lib/piwifi/__pycache__; fi
  rmdir /usr/local/lib/piwifi
fi
ln -s "$APP_DIR" "/usr/local/lib/.piwifi-$PIWIFI_RELEASE_ID"
mv -Tf "/usr/local/lib/.piwifi-$PIWIFI_RELEASE_ID" /usr/local/lib/piwifi
install -d -o root -g root -m 0755 /var/lib/piwifi-events
install -o root -g root -m 0440 "$release/sudoers" /etc/sudoers.d/piwifi-web
for unit in piwifi-web.service piwifi-observer.service piwifi-guard.service piwifi-guard.timer; do
  install -o root -g root -m 0644 "$release/$unit" "/etc/systemd/system/$unit"
done
if [[ ! -f /etc/piwifi-web.env ]]; then
  umask 077
  printf 'PIWIFI_USER=admin\nPIWIFI_PASS=%s\nPIWIFI_SECRET=%s\n' "$(openssl rand -hex 10)" "$(openssl rand -hex 32)" > /etc/piwifi-web.env
  echo 'Credentials created in root-only /etc/piwifi-web.env'
fi
systemctl daemon-reload
systemctl enable piwifi-web piwifi-observer piwifi-guard.timer
systemctl start piwifi-web piwifi-observer piwifi-guard.timer

ln -sfn "$APP_DIR/helper/piwifi-dns-sync" /usr/local/sbin/piwifi-dns-sync
install -o root -g root -m 0755 systemd/90-piwifi-dns /etc/NetworkManager/dispatcher.d/90-piwifi-dns
/usr/local/sbin/piwifi-dns-sync
echo "Activated complete release: $release"

# Session agent runs as the desktop user, never root. Browser starts only on request.
install -d -m 0755 /etc/systemd/user
install -o root -g root -m 0644 "$release/pi-media.service" "$release/pi-media-browser.service" /etc/systemd/user/
install -o root -g root -m 0644 "$release/pi-camera.service" /etc/systemd/user/
uid="$(id -u "$APP_USER")"
if [[ -S /run/user/$uid/bus ]]; then
  runuser -u "$APP_USER" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user daemon-reload
  runuser -u "$APP_USER" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user enable pi-media
  runuser -u "$APP_USER" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart pi-media
  runuser -u "$APP_USER" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user enable pi-camera
  runuser -u "$APP_USER" -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart pi-camera
fi
