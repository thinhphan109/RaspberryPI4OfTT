# Dashboard 3.6 — Pi Media

Adds authenticated/CSRF-protected Media control of one dedicated Chromium profile.
Play/pause, ±10sec seek, video volume, canonical YouTube video links, RAM queue50,
automatic ended-event queue advance, current title/thumbnail/time/ad indication.
No arbitrary URL, JavaScript or shell command endpoint. Unix agent socket0600;
Chrome debugging127.0.0.1:18769 only. Dedicated native Chromium binary avoids
desktop-global extensions; hardware sandbox/certificate validation stay enabled.

Follow-up18/10: official uBOL installed via scoped extension-ID machine policy on
Pi Chromium. Extensions and background networking are enabled for Web Store
updates; other Chromium profiles on the Pi also receive this policy. Default
filtering Optimal. YouTube's own autoplay is on and shown in Media status; no
queue is required for recommendations. Policy recovery is separate from deploy.

Nonstop follow-up: opt-in watchdog enabled at user's request,3sRAM loop, preserves
Dashboard manual pause, resumes regular pauses, confirms only recognized inactivity
dialog (never login/credential/terms), keeps autoplay, advances ended video and
recovers stalled180s/disconnected playback with60..900sbackoff. Explicit mode,
pause,seedURL andvolume changes persist0600; no durable periodic playback writes.
64Python+5Node checks passed; live manualpause/resume and10sconfig-no-write verified.
Hours-long inactivity and physical outages/reboot recovery remain untested.

Desktop session/keyring prerequisites remain. Agent enabled as user service;
browser starts on explicit request and is not enabled at boot. Opening Media does
not take over existing browser tabs. Profile/cookies stay under user home.

Deployment packages agent/client/UI/userunits and snapshots userunits. Pre-Media
rollback retires agent/browser while preserving profile. Agent restart drops queue.
Volume state starts35% after agent restart; navigation hook preserves selected
volume through later videos within a session. Keep a persistent CDP connection
because new-document hooks are attached to its lifetime.

See ops/MEDIA.md. Search integration, favorite playlists, EQ controls, timer and
screen streaming are outside this first release. Connect button links to existing
Raspberry Pi Connect, without provisioning it.
