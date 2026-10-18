#!/bin/bash
# Update the unprivileged camera bench only; keep one named rollback source.
set -euo pipefail
stage=${1:?Supply extracted source staging directory}
[[ "$stage" == /tmp/edgevision-update-* && -d "$stage/src/edgevision" ]]
base="$HOME/edgevision-camera"
[[ -d "$base/source" && -x "$base/venv/bin/python" ]]
PYTHONPATH="$stage/src" "$base/venv/bin/python" -B -m unittest discover -s "$stage/tests" -q
next="$base/source.next"
[[ ! -e "$next" ]]
mkdir "$next"
cp -a "$stage/src" "$next/src"
cp "$stage/pyproject.toml" "$next/"
backup="$base/source.before-analysis-$(date -u +%Y%m%dT%H%M%SZ)"
unit="$HOME/.config/systemd/user/edgevision-camera.service"
cp "$unit" "$backup.service"
systemctl --user stop edgevision-camera.service
mv "$base/source" "$backup"
mv "$next" "$base/source"
rollback() {
    systemctl --user stop edgevision-camera.service || true
    mv "$base/source" "$base/source.failed-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$backup" "$base/source"
    cp "$backup.service" "$unit"
    systemctl --user daemon-reload
    systemctl --user start edgevision-camera.service
}
trap rollback ERR
if [[ -f "$stage/ops/edgevision-camera.service" ]]; then
    cp "$stage/ops/edgevision-camera.service" "$unit"
    systemctl --user daemon-reload
fi
systemctl --user start edgevision-camera.service
for attempt in {1..20}; do
    if curl -fsS --max-time 2 http://127.0.0.1:18766/api/status; then
        echo
        echo "Source rollback: $backup"
        trap - ERR
        exit 0
    fi
    sleep 1
done
echo 'Camera bench did not become healthy; restoring source.' >&2
false
