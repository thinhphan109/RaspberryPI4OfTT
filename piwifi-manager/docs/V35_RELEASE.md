# Dashboard 3.5 — device DNS verification and Windows automation

DNS check returns `status`: verified, filter_error or unconfirmed, plus checked_at.
Session/CSRF/rate limits and random challenge privacy remain unchanged. UI checks
once on entering Apps, permits manual retry, shows a timestamp and invalidates
results when the Pi IP/network or supported browser connection signal changes.
It never equates an active service with proof of the browser's DNS route.

Windows watcher is per-user, opt-in, scheduled at logon with highest interactive
token. Immutable task payload is copied to Program Files; no sudoers/password
changes. A 30-second loop verifies SSH identity and DNS before changing only
WiFi IPv4 DNS. Three failed checks reset owned DNS to DHCP; later verified
recovery reapplies Pi DNS. External DNS changes suspend automation. No stable
IP or guaranteed discovery on multicast-isolated networks is claimed.

See `ops/DNS-AUTOMATION.md` for operation, limitations and validation. Complete
Pi-hole migration rollback and five dashboard snapshot retention remain as3.4.
