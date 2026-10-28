# Dashboard 3.4 — AdGuard Home migration

Deployed on 2026-10-15. AdGuard Home v0.107.79 replaces Pi-hole. Catalog, DNS
challenge verification and Windows Pi Control use the AdGuard API and service.
See `ops/ADGUARD.md` for daily use and migration recovery.

`piwifi-dns-sync` and NetworkManager dispatcher `90-piwifi-dns` replace the
Pi-hole-specific helper/hook. DNS binds localhost and current wlan0 private IPv4,
excluding the fallback AP and Tailscale. Unchanged addresses do not rewrite the
configuration. Address changes stop the service before editing, validate the
configuration and restore the prior bytes if validation fails. Startup prepares
the listen address before the DNS process starts.

Query log uses a bounded RAM buffer; statistics directories are in `/run`.
The dashboard still uses RAM observer history and does not log polling access.
Configuration/filter changes and unrelated host services can write to disk.

Migration was staged on alternate localhost ports, then checked over live
UDP/TCP 53 before deleting the inventoried Pi-hole runtime. Shared packages and
root-only recovery archives remain. A temporary independent migration recovery
timer protected cutover and was stopped after successful verification.

Validation: 50 Linux unit tests passed, live authenticated DNS challenge moved
from unseen to matched, blocking probe passed, all three catalog services were
active, and the Windows Pi Control UI check passed. Dashboard polling sample
showed zero process write_bytes over 20 seconds. Physical Wi-Fi moves, iPhone
interaction, boot/outage and AP-client tests were not performed in this release.

Deployment snapshots now record the DNS backend. Dashboard-only restore refuses
Pi-hole-era snapshots while AdGuard configuration exists; use the complete
root-only migration restore script for an intentional backend reversal.
