# 3.14.1 — Camera mở khi cần

User explicitly requests automatic webcam power based on viewing/recording,
plus a manual power button. See `ops/CAMERA.md`.

ViewerPower in existing camera_policy.py stores at most32 authenticated viewer
leases in RAM. Each document has a crypto-random128bit id; app scopes it with
SHA256(session-CSRF:id) before IPC. POST watch/automatic require CSRF, including
pagehide beacon body token. TTL15s, client heartbeat4s, no-view/no-record grace5s,
watchdog1s. GET/status/frame do not affect power demand.

Automatic defaults on; only explicit checkbox writes power.json. Manual off
is respected during current viewers; a fresh visit after all have left clears
the pause. Turning automatic off restores manual-only behavior. Active recording
always keeps camera and rejects manual power off; user must stop/render first.
No viewer triggers a printer command or starts a recording. Preview lease traffic
stops when the Camera view/document is hidden; pagehide and pageshow handle BFCache.
Unexpected browser termination expires by TTL, independent of reliable beacons.

Production deployment must wait for an existing user recording to finish, or
explicit user authorization to finish/render it. Do not restart camera to test
this feature during a user recording.

## Verified 2026-10-24

Release/snapshot `20261024T074343-135819`.
153 Python tests, camera JS lease/timer/pagehide/BFCache lifecycle test and
existing Node tests passed. Real production authenticated HTTP passed: auto
open, two viewers/one leaves, manual off across heartbeat/on, last-viewer idle,
no-view recording survival, rejection of power off during recording, automatic
rest after stop/render, abandoned viewer expiry. Actual FFmpeg exited at idle.
Idle agent sample0.033%onecore6seconds; no watt measurement. Real browser Camera
entry loaded1280px image with automatic checked;1366px no horizontal overflow.
Physical iPhone sleep/app switching, actual browser force-kill and long-run
network-loss timing remain pending; tests model expiry without release.
