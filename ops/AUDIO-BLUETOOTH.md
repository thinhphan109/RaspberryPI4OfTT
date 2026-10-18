# Dashboard audio and Bluetooth

Open Dashboard > **Âm thanh & Bluetooth** (`#audio`). Controls apply to Pi's
desktop audio, not the phone/browser opening the page. No browser mic permission
is requested and no audio is captured by Dashboard.

For a speaker/headset: enable its pairing mode, **Quét 6 giây**, choose the named
device, **Ghép nối**, then **Kết nối**. Existing paired devices can connect directly.
When its physical PipeWire output appears, choose **Dùng thiết bị này**. Volume
and mute apply to the selected physical node, bounded0–100%. The current analog
jack is `bcm2835 Headphones`. A microphone needs USB/Bluetooth hardware support;
the Pi3.5mmjack has no microphone input. Bluetooth headset mic availability depends
on its active profile; profile/codec switching is not implemented here.

EasyEffects remains enabled and follows the physical default device. Its virtual
sink/source are hidden to avoid a feedback/default-device loop. Device volume is
separate from Media video volume, sleep timer and scheduled cap. Changing output
may briefly interrupt sound; actual speaker audibility needs user verification.

Pairing is an explicit action to one discovered address, bounded15seconds and
NoInputNoOutput agent (headsets/speakers supporting this). No implicit trust,
discoverable mode or auto-pair for strangers is enabled. PIN/passkey devices may
need the Pi desktop; web PIN confirmation, device forgetting, incoming-phone
Bluetooth-speaker mode and auto-reconnect policy are outside this implementation.

Backend is audio_control.py loaded by existing same-user pi-media agent/private
0600Unix socket. Authenticated `/api/audio` uses CSRF on writes and fixed commands,
current PipeWire ID/kind validation, MAC validation, no shell. BlueZ scan/pair/
connect/disconnect run bounded background jobs, so they do not block player
controls. Normal status caches5seconds and UI polls8seconds only while visible.
No durable polling history added. BlueZ pairing/WirePlumber/gsettings changes are
ordinary explicit system settings outside source rollback. No new sudoers rule,
package or public port. Desktop user session and pi-media must be running.

Deployment3.10.0 finalrelease/snapshot20261018T125909-275162; root-only five recovery
snapshots retained.97Python tests plus Node chart/polling checks passed. Live
status, same-volume/same-default change and bounded Bluetooth discovery tested.
Current headsetUGREEN HiTuneS3 is paired but disconnected; no unsolicited pairing
or connection attempted. New physical pairing/audio transfer/microphone recording
have not been tested; do not claim those passed.
