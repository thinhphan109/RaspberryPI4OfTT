# Log2ram on RaspberryPI4OfTT

Installed and boot-verified on 2026-10-14 at 192.168.0.106 using the dedicated
rasp-tt SSH key and temporary sudo. No sudoers changes were made.

## Installed source and policy

- Upstream: https://github.com/azlux/log2ram
- Pinned commit: a6bc20ad038ec8b3341fca6b653c5094ee3f8524
- Reviewed upstream files and MIT license: `ops/vendor/log2ram/`.
- Manual installation, not an APT package; future updates must be reviewed explicitly.
- Root entrypoint: `ops/install-log2ram.sh`; refuses an existing installation or
  existing backing directories and refuses logs larger than 64 MiB.
- `/var/log`: tmpfs, capacity 128 MiB; `/var/hdd.log`: bind mount of the original
  SD-backed log directory. The RAM volume does not reserve its full capacity upfront.
- Daily sync at 23:55 Asia/Ho_Chi_Minh, plus sync on a normal service stop/shutdown.
- rsync enabled; zram integration disabled. Existing host zram/swap unchanged.
- Existing journald `Storage=volatile` unchanged: journals under `/run` are not
  persisted by this installation. Dashboard RAM history unchanged.
- Full-volume mail notifications disabled because no mail delivery is configured;
  upstream still logs startup errors. Existing logrotate remains enabled.

## Verified after reboot

- `/var/log` source `log2ram`, filesystem `tmpfs`, mount options
  `rw,nosuid,nodev,noexec,noatime,size=131072k,mode=755`.
- RAM log usage approximately 900 KiB; host swap usage 0 B at observation.
- `/var/hdd.log` points to `/dev/mmcblk0p2[/var/log]`, filesystem ext4.
- log2ram startup copy succeeded; unit Result=success, ExecMainStatus=0.
- log2ram and its daily timer enabled; next sync shown as 2026-10-14 23:55 +07.
- piwifi-web, piwifi-observer, piwifi-guard.timer, cloudflared active.
- Local `/login` returned HTTP 200; wlan0 connected at 192.168.0.106/24.
- systemd reported zero failed units. Uploaded staging files removed.

The daily sync and shutdown flush were not separately forced after installation;
the configured timer/ExecStop were inspected. Physical power-loss/outage/AP-client
tests remain pending. This is not a measured percentage reduction in total host
SD writes: journald was already volatile and other application data still writes
to the SD. Unsynced RAM logs are lost on unexpected power loss. tmpfs may use swap
under memory pressure; the host's existing swap backing policy was not changed.

## Recovery and operations

Root-only installation record and restore entrypoint on the Pi:

`/var/lib/pi-ops/log2ram-20261014T151349Z/restore.sh`

After temporary sudo authentication, run that restore entrypoint with `sudo` to
flush and unmount the RAM logs, disable/remove the installed files, and preserve
original disk logs. Reboot afterward to reopen application log file descriptors.
Do not delete `/var/hdd.log` or run the upstream install script over this setup:
upstream install clears previous backing folders.

Read-only checks:

```sh
findmnt -M /var/log
df -h /var/log
systemctl status log2ram --no-pager
systemctl list-timers log2ram-daily.timer --no-pager
journalctl -u log2ram -b -n 30 --no-pager
```

Explicit manual flush, when needed: `sudo systemctl reload log2ram.service`.
Watch RAM volume growth before adding high-volume file loggers; new applications
need their own bounded log rotation. Data outside `/var/log` is not covered.
