# Dashboard 3.7 — upcoming video and scheduled volume cap

Media shows the canonical next video from YouTube's player next button, with
its title matched to the recommendation metadata. Explicit RAM queue takes
priority. Skip moves to the current recommendation, which YouTube may change;
the preview is not a pinned playlist. External URLs are rejected server-side.

One optional daily volume window uses Asia/Ho_Chi_Minh, supports crossing
midnight, includes start and excludes end. Defaults are disabled,22:00–07:00,30%.
Configure and save in Media > volume schedule. Equal start/end is rejected.
The cap applies to the dedicated Media video's volume, not PipeWire/system,
other browser profiles or EasyEffects output gain. It runs independently of
Nonstop and manual pause. Manual commands are clamped; a3sRAM loop lowers an
existing video's level and refreshes the navigation volume hook. Ending the
window does not raise the volume. No hard real-time guarantee at the boundary.

Explicit settings persist atomically0600 in the existing user's
~/.local/state/pi-media/nonstop.json. Playback ticks do not write settings.
Schedule loads even when no initial video URL was saved. Agent restart still
loses the RAM queue. Normal user browser state/cookies retain existing writes.

Also fixes empty-queue indexing after Nonstop advances an ended video. Existing
auth/CSRF and private CDP/socket boundaries are retained. Browser is not restarted
by deployment; playback should continue while the agent reconnects.

Validation:72Python tests and5Node inactivity-dialog checks passed on18October.
Live checks and deployment reference are recorded in ops/MEDIA.md.
