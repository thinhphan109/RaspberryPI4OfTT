# Dashboard 3.8 — local dislikes, sleep and repeat protection

Media adds local **Không thích bài này**, sleep timer1–720minutes, and default-on
3hour repeat protection (configurable1–24hours). No YouTube account rating is sent.
Dislikes are bounded200video IDs/titles, persisted on explicit actions, and can be
removed individually. Direct Play permits recent videos but rejects disliked ones.

Next selection prefers eligible queue entries, then the YouTube next button and
up to40visible recommendation titles. Current video, disliked and recent IDs are
excluded. A3sRAM watchdog checks automatic native navigation too. History holds
up to500transitions and resets on agent restart/reboot. This is exact video-ID
matching: alternate uploads of the same song are not recognized as duplicates.
If no eligible candidate exists, playback pauses with guidance rather than looping
through excluded videos. Network/YouTube availability still affects recommendations.

Sleep fades only downward through the last120seconds (or the whole timer if
shorter), then pauses the dedicated video and disables its YouTube autoplay.
Sleep expiry takes priority over Nonstop, recovery and queue advance. An expired
latch is kept until explicit Play/Play now; it restores the starting video volume
subject to the time-of-day cap. Cancelling an active timer keeps current volume.
No whole-Pi shutdown or other application audio control is performed.

The deadline and initial volume persist in the existing0600config on explicit
timer creation. Monotonic time is used within a process; loading uses remaining
wall time bounded by original duration. An expired saved deadline remains a stop
latch after agent restart. Periodic fade/expiry/history do not write config.
Normal Chromium profile writes remain. Pausing/fading has a3scheck interval and
requires an accessible desktop player. Downgrading to pre3.8 removes this timer
enforcement; do not rely on the latch through such a rollback.

New pure policy module media_policy.py is included in installer, deploy allowlist
and AST checks. UI retains auth/CSRF and private socket/loopback CDP boundaries.
See ops/MEDIA.md for deployed verification and recovery reference.
