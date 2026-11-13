#!/usr/bin/env python3
"""Prepare a reversible one-boot Wi-Fi recovery on the identified Pi SSD FAT.

Only writes files on the selected boot partition; never formats/mounts ext4.
The client passphrase is derived to a WPA2 PSK. An optional hotspot passphrase
is staged only for the next boot, then removed by the recovery runner.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import uuid

from offline_wifi_boot import PREFIX, BOOT_ARGUMENTS, atomic_write, validate_fallback_password

ROOT_UUID = '98a7c93a-53ab-4f91-b51e-0bbccfc1fff2'
HOST_FINGERPRINT = 'SHA256:j/SxiZZCzRAgjb6UrvPERTSil40V9sRNUzyZ1HR0RSY'
ROOT_CMDLINE_ARG = 'root=PARTUUID=9586d7bf-02'


def prepare(boot, ssid, password, *, fallback_password=None):
    if not 1 <= len(ssid.encode('utf-8')) <= 32 or any(c in ssid for c in '\r\n\\;'):
        raise ValueError('Invalid SSID')
    if not 8 <= len(password.encode('utf-8')) <= 63: raise ValueError('Invalid WPA2 passphrase length')
    original = (boot / 'cmdline.txt').read_bytes()
    line = original.decode('ascii').strip()
    if ROOT_CMDLINE_ARG not in line.split() or 'systemd.run=' in line or 'systemd.unit=' in line:
        raise ValueError('Unexpected root partition or existing boot override; refusing to edit')
    if not (boot / 'config.txt').is_file(): raise ValueError('Not a Pi boot partition')
    for suffix in ('.json', '.cmdline', '.nmconnection', '.py'):
        if (boot / (PREFIX + suffix)).exists(): raise ValueError('Recovery already staged')
    identifier = secrets.token_hex(4)
    psk = hashlib.pbkdf2_hmac('sha1', password.encode(), ssid.encode(), 4096, 32).hex()
    payload = (f'[connection]\nid=Pi-Control-Recovery-{identifier}\nuuid={uuid.uuid4()}\n'
               'type=wifi\ninterface-name=wlan0\nautoconnect=true\nautoconnect-priority=100\n'
               'autoconnect-retries=2\n[802-11-wireless]\nmode=infrastructure\n'
               f'ssid={ssid}\n[802-11-wireless-security]\nkey-mgmt=wpa-psk\npsk={psk}\n'
               '[ipv4]\nmethod=auto\n[ipv6]\nmethod=auto\n').encode()
    plan = dict(root_uuid=ROOT_UUID, host_fingerprint=HOST_FINGERPRINT, ssid=ssid,
                cmdline_sha256=hashlib.sha256(original).hexdigest(),
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                profile_filename=f'pi-control-recovery-{identifier}.nmconnection')
    if fallback_password is not None:
        validate_fallback_password(fallback_password)
        plan['fallback_password'] = fallback_password
    created = []
    try:
        for suffix, data in (('.cmdline', original), ('.nmconnection', payload),
                             ('.json', (json.dumps(plan) + '\n').encode()),
                             ('.py', Path(__file__).with_name('offline_wifi_boot.py').read_bytes())):
            path = boot / (PREFIX + suffix)
            atomic_write(path, data); created.append(path)
        # Arm last, only after all payload files are durable.
        atomic_write(boot / 'cmdline.txt', (line + ' ' + BOOT_ARGUMENTS + '\n').encode())
        if hasattr(os, 'sync'): os.sync()
    except Exception:
        atomic_write(boot / 'cmdline.txt', original)
        for path in created: path.unlink(missing_ok=True)
        raise
    return dict(ok=True, boot=str(boot), ssid=ssid, root_uuid=ROOT_UUID,
                original_cmdline_sha256=plan['cmdline_sha256'],
                automatic_reboots=1, fallback_updated=False,
                fallback_update_staged=fallback_password is not None,
                requires_boot_verification=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--ssid', required=True)
    parser.add_argument('--change-fallback-password', action='store_true')
    args = parser.parse_args()
    passphrase = getpass.getpass('Wi-Fi passphrase (not echoed): ')
    fallback = getpass.getpass('New fallback passphrase (not echoed): ') if args.change_fallback_password else None
    print(json.dumps(prepare(args.boot, args.ssid, passphrase, fallback_password=fallback), ensure_ascii=False))
