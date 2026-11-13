#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then exec sudo -n bash "$0"; fi
[[ ! -f /etc/pi-control/runtime.json ]] || { echo 'Modular SSD system: use the SSD bootstrap installer per module'; exit 1; }
exec 9>/run/lock/piwifi-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
exec 10>/run/piwifi-network.lock
flock -w 180 10 || { echo 'A network transition is still running'; exit 1; }
export PIWIFI_DEPLOY_LOCKED=1
export PIWIFI_RELEASE_ID="$(date -u +%Y%m%dT%H%M%S)-$$"
cd "$(dirname "$0")/.."
command -v nmcli >/dev/null
# Do not cut off a recording or its renderer during a source switch.
if [[ -f /opt/piwifi-web/camera.py ]]; then
  runuser -u thinh -- python3 -B - <<'PY'
import sys
sys.path.insert(0, '/opt/piwifi-web')
import camera
try:
    data = camera.call({'action':'status'})
except (OSError, RuntimeError, ValueError):
    raise SystemExit('Cannot verify camera state; deployment stopped before changes')
if data.get('recording') or data.get('rendering'):
    raise SystemExit('Camera is recording/rendering; finish the session before deploying')
PY
fi
python3 - <<'PY'
import ast
for p in ('pi-control/camera.py','pi-control/camera_agent.py','pi-control/camera_policy.py','pi-control/media.py', 'pi-control/media_agent.py', 'pi-control/media_policy.py','pi-control/media_extras.py','pi-control/media_catalog.py','pi-control/youtube_quality.py','pi-control/spotify_player.py','pi-control/native_player.py', 'pi-control/audio_control.py','pi-control/storage_writes.py', 'pi-control/system_events.py', 'pi-control/app.py','pi-control/read_cache.py','pi-control/runtime_config.py','pi-control/audio_agent.py','pi-control/audio_client.py','pi-control/camera_renderer.py','pi-control/render_jobs.py','pi-control/service_catalog.py','pi-control/deployment_history.py', 'pi-control/hub.py', 'pi-control/helper/piwifi-dns-sync', 'pi-control/metrics.py', 'pi-control/observer.py', 'pi-control/state.py', 'pi-control/mcp_server.py', 'pi-control/hardware.py', 'pi-control/security.py', 'pi-control/helper/piwifi-helper', 'pi-control/helper/piwifi-guard'):
    with open(p, encoding='utf-8') as f:
        ast.parse(f.read(), filename=p)
PY
# A root-only snapshot covers precisely the components modified by install.sh.
base=/var/lib/piwifi-deploy
install -d -o root -g root -m 0700 "$base"
snapshot="$base/$PIWIFI_RELEASE_ID"
mkdir -m 0700 "$snapshot"
if [[ -f /opt/piwifi-web/apps.json ]] && python3 -c 'import json; assert any(a.get("service")=="adguardhome" for a in json.load(open("/opt/piwifi-web/apps.json")))' 2>/dev/null; then
  printf adguardhome > "$snapshot/dns-backend"
else
  printf pihole > "$snapshot/dns-backend"
fi
paths=(opt/piwifi-web usr/local/lib/piwifi usr/local/sbin/piwifi-helper usr/local/sbin/piwifi-guard usr/local/sbin/wifi-fallback-guard etc/piwifi-web.env etc/sudoers.d/piwifi-web etc/systemd/system/piwifi-web.service etc/systemd/system/piwifi-guard.service etc/systemd/system/piwifi-guard.timer etc/systemd/system/piwifi-observer.service var/lib/piwifi-events/release.json)
existing=()
paths+=(etc/systemd/user/pi-media.service etc/systemd/user/pi-media-browser.service usr/local/sbin/piwifi-dns-sync etc/NetworkManager/dispatcher.d/90-piwifi-dns etc/adguardhome/AdGuardHome.yaml usr/local/sbin/piwifi-pihole-sync etc/NetworkManager/dispatcher.d/90-piwifi-pihole etc/pihole/pihole.toml)
paths+=(etc/systemd/user/pi-camera.service)
if [[ -L /opt/piwifi-web ]]; then
  release="$(readlink -f /opt/piwifi-web)"
  [[ "$(dirname "$release")" == /opt/piwifi-releases ]] || { echo 'Unexpected release target'; exit 1; }
  existing+=("${release#/}")
fi
for p in "${paths[@]}"; do
  if [[ -e /$p || -L /$p ]]; then existing+=("$p"); fi
done
tar -czpf "$snapshot/files.tar.gz" -C / "${existing[@]}" --files-from /dev/null
systemctl is-active --quiet piwifi-web && touch "$snapshot/was-active" || true
systemctl is-enabled --quiet piwifi-web && touch "$snapshot/was-enabled" || true
systemctl is-enabled --quiet piwifi-guard.timer && touch "$snapshot/guard-enabled" || true
systemctl is-active --quiet piwifi-guard.timer && touch "$snapshot/guard-active" || true
systemctl is-active --quiet piwifi-observer && touch "$snapshot/observer-active" || true
systemctl is-enabled --quiet piwifi-observer && touch "$snapshot/observer-enabled" || true
runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active --quiet pi-camera && touch "$snapshot/camera-active" || true
runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-enabled --quiet pi-camera && touch "$snapshot/camera-enabled" || true
cat > "$snapshot/restore.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 1
if [[ ${PIWIFI_DEPLOY_LOCKED:-0} != 1 ]]; then
  exec 9>/run/lock/piwifi-deploy.lock
  flock -n 9 || exit 1
  exec 10>/run/piwifi-network.lock
  flock -w 180 10 || exit 1
fi
cd "$(dirname "$(readlink -f "$0")")"
if [[ -f /etc/adguardhome/AdGuardHome.yaml && "$(cat dns-backend 2>/dev/null || printf pihole)" != adguardhome ]]; then
  echo 'DNS backend changed. Use /var/lib/adguard-migration/restore.sh for a complete Pi-hole migration rollback.'
  exit 1
fi
systemctl disable --now piwifi-web 2>/dev/null || true
systemctl disable --now piwifi-guard.timer 2>/dev/null || true
systemctl stop piwifi-guard.service 2>/dev/null || true
systemctl disable --now piwifi-observer 2>/dev/null || true
runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user disable --now pi-camera 2>/dev/null || true
# Fixed project-owned destinations; reject directories replaced by symlinks.
if [[ -L /opt/piwifi-web ]]; then
  [[ "$(dirname "$(readlink -f /opt/piwifi-web)")" == /opt/piwifi-releases ]] || exit 1
  rm -f -- /opt/piwifi-web
else
  rm -rf -- /opt/piwifi-web
fi
rm -f -- /usr/local/sbin/piwifi-helper /etc/piwifi-web.env /etc/sudoers.d/piwifi-web /etc/systemd/system/piwifi-web.service
rm -f -- /usr/local/sbin/piwifi-guard /etc/systemd/system/piwifi-guard.service /etc/systemd/system/piwifi-guard.timer
if [[ -L /usr/local/lib/piwifi ]]; then
  [[ "$(readlink /usr/local/lib/piwifi)" == /opt/piwifi-web ]] || exit 1
  rm -f -- /usr/local/lib/piwifi
else
  rm -rf -- /usr/local/lib/piwifi
fi
rm -f -- /etc/systemd/system/piwifi-observer.service /var/lib/piwifi-events/release.json
rm -f -- /usr/local/sbin/piwifi-dns-sync /etc/NetworkManager/dispatcher.d/90-piwifi-dns /usr/local/sbin/piwifi-pihole-sync /etc/NetworkManager/dispatcher.d/90-piwifi-pihole
tar -xzpf files.tar.gz -C /
if [[ ! -f /opt/piwifi-web/camera_agent.py ]]; then
  rm -f /etc/systemd/user/pi-camera.service
fi
# Restore matching user-agent units, or retire them for a pre-Media release.
if [[ ! -f /opt/piwifi-web/media_agent.py ]]; then
  runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user disable --now pi-media pi-media-browser 2>/dev/null || true
  rm -f /etc/systemd/user/pi-media.service /etc/systemd/user/pi-media-browser.service
fi
runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user daemon-reload 2>/dev/null || true
if [[ -f /opt/piwifi-web/camera_agent.py ]]; then
  if [[ -f camera-enabled ]]; then runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user enable pi-camera; fi
  if [[ -f camera-active ]]; then runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user start pi-camera; fi
fi
if [[ -f /opt/piwifi-web/media_agent.py ]]; then
  runuser -u thinh -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart pi-media
fi
systemctl daemon-reload
if [[ -f was-enabled ]]; then systemctl enable piwifi-web; fi
if [[ -f was-active ]]; then systemctl start piwifi-web; fi
if [[ -f guard-enabled ]]; then systemctl enable piwifi-guard.timer; fi
if [[ -f guard-active ]]; then systemctl start piwifi-guard.timer; fi
if [[ -f observer-enabled ]]; then systemctl enable piwifi-observer; fi
if [[ -f observer-active ]]; then systemctl start piwifi-observer; fi
if systemctl is-enabled --quiet adguardhome 2>/dev/null; then systemctl restart adguardhome; elif command -v pihole-FTL >/dev/null; then systemctl restart pihole-FTL; fi
SH
chmod 0700 "$snapshot/restore.sh"
ln -sfn "$snapshot" "$base/latest"
trap 'rc=$?; echo "Deploy failed; restoring snapshot"; bash "$snapshot/restore.sh"; exit "$rc"' ERR
cd pi-control
bash scripts/install.sh
python3 - <<'PY'
import time, urllib.request
for attempt in range(15):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:18765/login', timeout=2) as r:
            if r.status == 200:
                break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('Web health check failed')
PY
systemctl is-active --quiet piwifi-web
systemctl is-active --quiet piwifi-guard.timer
systemctl is-active --quiet piwifi-observer
python3 - <<'PY'
import hashlib, json, time, sys
from pathlib import Path
sys.path.insert(0, '/usr/local/lib/piwifi')
import state
digest = hashlib.sha256()
for p in sorted(Path('/opt/piwifi-web').rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts:
        digest.update(str(p.relative_to('/opt/piwifi-web')).encode())
        digest.update(p.read_bytes())
state.write('release.json', dict(version='4.2.0', timestamp=int(time.time()), source_hash=digest.hexdigest(), release=Path('/opt/piwifi-web').resolve().name))
state.event('deploy', 'Đã triển khai dashboard 4.2.0 và kiểm tra dịch vụ')
PY
# Retire the unscheduled legacy guard; its exact previous bytes are in the snapshot.
rm -f -- /usr/local/sbin/wifi-fallback-guard
trap - ERR
# Upgrade the restore runner for retained legacy archives; archived file bytes stay unchanged.
for old in "$base"/*/restore.sh; do
  [[ "$(readlink -f "$old")" == "$snapshot/restore.sh" ]] || install -o root -g root -m 0700 "$snapshot/restore.sh" "$old"
done
printf 'Deploy verified. Rollback snapshot: %s\n' "$snapshot"
# Keep five snapshots, including the just-created known restoration point.
python3 - <<'PY'
from pathlib import Path
import re, shutil
base = Path('/var/lib/piwifi-deploy')
latest = (base / 'latest').resolve()
items = sorted((p for p in base.iterdir() if not p.is_symlink() and p.is_dir() and re.fullmatch(r'\d{8}T\d{6}-\d+', p.name)), reverse=True)
for p in items[5:]:
    if p != latest and p.resolve().parent == base:
        shutil.rmtree(p)
# Archives include complete referenced releases, so an older release can be restored after pruning.
release_base = Path('/opt/piwifi-releases')
current = Path('/opt/piwifi-web').resolve()
releases = sorted((p for p in release_base.iterdir() if p.is_dir() and not p.is_symlink() and re.fullmatch(r'(?:legacy-)?\d{8}T\d{6}-\d+', p.name)), reverse=True)
keep = set(releases[:3]) | {current}
for p in releases:
    if p not in keep and p.resolve().parent == release_base:
        shutil.rmtree(p)
PY
printf 'Retention: five root-only restoration snapshots.\n'
