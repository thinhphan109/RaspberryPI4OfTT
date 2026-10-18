# ESP32 camera bench on Raspberry Pi

## Dataset update, 2026-10-15

`/dataset` adds explicit raw-JPEG capture, manual boxes/class editing, draft and
review state, confirmed empty-background images, session-bound train/val/test
splits and YOLO ZIP export. Main data excludes trial and unreviewed images by
default; optional trial export still requires reviewed images. User confirmed
LED has not been addressed. No production labels were approved or training run.

Persistent dataset path: `/home/thinh/edgevision-camera/data/dataset`, passed
via `--dataset-dir` in the user unit. Image limit1000 and64MiB of image bytes;
metadata additional. Exact-JPEG duplicates rejected; near duplicates not inferred.
Image data immutable, annotation revisions atomic; unchanged saves do not write.
Export ZIP built in bounded RAM, no temporary ZIP on SD. Reads/index use cached
metadata; no periodic dataset capture/polling or deletion.

Latest full source/unit snapshot: `source.before-analysis-20261015T052508Z` under
`/home/thinh/edgevision-camera`, matching `.service`. A later atomic JavaScript
fix removed the SVG hidden attribute; source is in the PC project. Dataset data
is outside source and is not reverted by source rollback.

37 tests passed on Pi and PC, plus live browser capture/manual coordinate and
drag-box/draft/reload checks. Live10read rounds: unchanged file inventory,
application write_bytes delta0; original JPEG SHA verified. One29,486-byte trial
image179522f0153e4963b0605b7ea7cf6b8e with2draft boxes, reviewed=false. Do not
claim this is human-approved training data. No MCU firmware change this phase.
Guide: `D:/1. WorkSpace/EdgeVisionRobot/docs/13_DATASET_WORKFLOW.md`.

## Image-analysis update, 2026-10-15

This section supersedes the initial HSV-only/no-flash state below. User targets:
black USB stick, yellow pencil sharpener, round blue bottle cap. Pi now runs
`--baseline tabletop`: colour/shape candidates, not trained semantic AI.
Current source includes ROI and original-image quality diagnostics; preview
still does not persist image data. Actual overlaps caused misses/merged regions.

ESP32 application was updated (app partition only, esptool hash verified) after
full16MiB backup. Camera exposes bounded exposure/WB/manual gain/LENC controls;
no network credential/partition/NVS changes. Current sensor profile is manual
885lines, gain7 (raw111), WB0, LENC1. Settings are RAM-only and reset after ESP
reboot. No public API/tunnel added. Pi HTTP control validates same Origin,
whitelisted integer ranges and canonical application order. These are not
atomic multi-setting hardware transactions; read back after any failure.

Final source rollback: `/home/thinh/edgevision-camera/source.before-analysis-20261015T050511Z`
and matching `.service` file. Original pre-analysis source is also retained;
two intermediate source snapshots and all uploaded staging were removed.
For latest rollback: stop user unit, preserve current source under a new name,
restore that source directory and its matching unit, daemon-reload, then start.
Collected data remains outside source. No rollback was forced in this update.

29 tests passed on Pi. Final10preview mean219.4ms/request, no persistent data
changes; explicit Analyze creates JPEG+JSONL. Original metrics still heuristic,
no independently evaluated AI accuracy or sustained CPU/FPS benchmark. Tests
with manual exposure on a new white-paper layout produced three candidates in
10/10 stationary frames; this does not establish performance for changed poses,
overlaps, lighting or background. Scene changed during tests, so automatic vs
manual trials are not controlled causal A/B measurements.

Full report: `D:/1. WorkSpace/EdgeVisionRobot/docs/12_CAMERA_TARGETS_AND_EXPOSURE.md`.

## Initial deployment record

Verified 2026-10-15. ESP32 native USB Serial/JTAG is COM21 on the PC. Port
opened successfully at 115200 without asserting DTR/RTS; no unsolicited output.
Existing firmware responded over LAN; no flash, erase, or firmware change made.
Serial port was closed after inspection.

## Running deployment

- ESP32: `http://192.168.0.104/api/frame`, status `/api/status`.
- Existing EdgeVisionRobot firmware 0.1.0, station mode, VGA JPEG. Autofocus
  reports not enabled. Observed image is tilted and dim; not calibration-ready.
- Pi: 192.168.0.106, user thinh; Python 3.13.5, isolated virtual environment.
- Application copied from `D:/1. WorkSpace/EdgeVisionRobot/src/edgevision` and
  `pyproject.toml`. Firmware, local config, backups and runtime secrets excluded.
- Source: `/home/thinh/edgevision-camera/source`; virtual environment: `venv`
  within the same parent. This is a deployed copy, not a live mount of PC source.
- Unit: `/home/thinh/.config/systemd/user/edgevision-camera.service`, enabled
  under the existing user manager (Linger was already yes; unchanged).
- Loopback only: `http://127.0.0.1:18766` on Pi. No public tunnel or LAN listener
  added. Source interface has no authentication, so keep it loopback-only.
- Run data: `/home/thinh/edgevision-camera/data/captures`; calibration data:
  `/home/thinh/edgevision-camera/data/calibration`.
- HSV baseline only, no YOLO model; no robot motion enabled.
- Preview does not save image files. Explicit Analyze saves raw JPEG and JSONL.
  Calibration actions can also save data. Dataset writes are intentional and are
  outside log2ram coverage. No dataset retention/deletion automation added.
- Unit specifies CPUQuota=100% and MemoryMax=384M; controller enforcement has
  not been verified (MemoryCurrent unavailable). Do not claim enforced limits.

## Access from this PC

An SSH forwarding session was opened for the delivered browser. Reopen it after
the tunnel closes using PowerShell (keep this command running; Ctrl+C stops it):

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 -o HostName=192.168.0.106 -o HostKeyAlias=raspberrypi.local -o StrictHostKeyChecking=yes -L 127.0.0.1:18766:127.0.0.1:18766 rasp-tt
```

Then visit http://127.0.0.1:18766 . Choose raw preview to avoid HSV overlays;
continuous view stops when the tab becomes hidden. Analysis uses traditional
color segmentation, not trained AI. Stop preview when not needed.

## Validation

- Existing project: 19 Windows unit tests passed.
- On-Pi check: `ops/verify-edgevision-camera.py` received 10/10 valid decoded
  640x480 JPEG previews, increasing device sequences 2..11, mean173.0ms/request.
  This is a short sequential test, not a sustained FPS or AI benchmark.
- Before/after persistent data inventory unchanged over previews.
- One explicit Analyze created one raw JPEG and one frames.jsonl; no robot motion.
- Real Edge browser confirmed live camera image through PC -> SSH -> Pi -> ESP32.
  Preview stopped after verification; tab retained for user.
- Pi app listens only 127.0.0.1:18766. Existing Pi dashboard and guard untouched.
- Uploaded temporary archive/test script removed; no firmware changes.

## Service operations

On Pi, as thinh:

```sh
systemctl --user status edgevision-camera --no-pager
systemctl --user restart edgevision-camera
systemctl --user disable --now edgevision-camera
```

Disable stops the app and prevents autostart without deleting collected images.
To change a camera IP, update the service's --camera argument, daemon-reload and
restart it. Source/dependencies/unit templates must be reviewed before updates.
Do not expose this development server via Cloudflare or bind 0.0.0.0 without
adding authentication and reviewing request handling.
