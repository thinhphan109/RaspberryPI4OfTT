#!/usr/bin/python3 -B
"""One boot only: provision a Wi-Fi profile on the verified Pi SSD, then reboot.

No Wi-Fi credential is embedded in this source. The temporary boot payload is
removed, and the exact original kernel command line is restored on either path.
"""
import configparser
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

PREFIX = 'pi-control-net-recovery'
BOOT_ARGUMENTS = ('systemd.run="/usr/bin/python3 -B /boot/firmware/' + PREFIX + '.py" '
                  'systemd.run_success_action=reboot systemd.run_failure_action=none '
                  'systemd.unit=kernel-command-line.target')


def atomic_write(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.recovery-' + secrets.token_hex(6) + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def identity():
    root_uuid = subprocess.check_output(
        ['/usr/bin/findmnt', '-n', '-o', 'UUID', '/'], text=True, timeout=5).strip()
    fingerprint = subprocess.check_output(
        ['/usr/bin/ssh-keygen', '-lf', '/etc/ssh/ssh_host_ed25519_key.pub'],
        text=True, timeout=5).split()[1]
    return root_uuid, fingerprint


def validate_fallback_password(password):
    if (not isinstance(password, str) or not 8 <= len(password) <= 63
            or any(not 33 <= ord(char) <= 126 or char == '\\' for char in password)):
        raise ValueError('invalid-hotspot-passphrase')


def update_fallback(system_root, password):
    validate_fallback_password(password)
    profile = system_root / 'etc/NetworkManager/system-connections/pi-control-fallback.nmconnection'
    access = system_root / 'etc/pi-control/network/fallback-access.json'
    if any(path.is_symlink() or not path.is_file() for path in (profile, access)):
        raise ValueError('missing-or-unexpected-hotspot-configuration')
    original_profile, original_access = profile.read_bytes(), access.read_bytes()
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(original_profile.decode('utf-8'))
    if (config['connection']['id'] != 'Pi-Fallback'
            or config['802-11-wireless']['ssid'] != 'RaspPI4OfTT'
            or config['802-11-wireless']['mode'] != 'ap'):
        raise ValueError('unexpected-hotspot-profile')
    credentials = json.loads(original_access)
    if credentials['ssid'] != 'RaspPI4OfTT':
        raise ValueError('unexpected-hotspot-access-record')
    config['802-11-wireless-security']['psk'] = password
    output = StringIO()
    config.write(output, space_around_delimiters=False)
    credentials['password'] = password
    atomic_write(profile, output.getvalue().encode())
    try:
        atomic_write(access, (json.dumps(credentials) + '\n').encode())
    except OSError:
        atomic_write(profile, original_profile)
        raise


def recover(boot=Path('/boot/firmware'), system_root=Path('/'), probe=identity):
    result = {'ok': False, 'wifi_connected': 'not-tested', 'fallback_updated': False}
    original = None
    plan = {}
    try:
        plan = json.loads((boot / (PREFIX + '.json')).read_text())
        original = (boot / (PREFIX + '.cmdline')).read_bytes()
        if hashlib.sha256(original).hexdigest() != plan['cmdline_sha256']:
            original = None
            raise ValueError('original-cmdline-checksum-mismatch')
        if probe() != (plan['root_uuid'], plan['host_fingerprint']):
            raise ValueError('Pi-SSD-identity-mismatch')
        payload = (boot / (PREFIX + '.nmconnection')).read_bytes()
        if hashlib.sha256(payload).hexdigest() != plan['payload_sha256']:
            raise ValueError('wifi-payload-checksum-mismatch')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(payload.decode('utf-8'))
        if config['802-11-wireless']['ssid'] != plan['ssid']:
            raise ValueError('wifi-SSID-mismatch')
        if not re.fullmatch('[a-f0-9]{64}', config['802-11-wireless-security']['psk']):
            raise ValueError('expected-derived-WPA2-key')
        filename = plan['profile_filename']
        if not re.fullmatch(r'pi-control-recovery-[a-f0-9]{8}\.nmconnection', filename):
            raise ValueError('invalid-profile-destination')
        target = system_root / 'etc/NetworkManager/system-connections' / filename
        if not target.parent.is_dir() or target.is_symlink():
            raise ValueError('invalid-NetworkManager-directory')
        if target.exists() and target.read_bytes() != payload:
            raise ValueError('refusing-to-overwrite-existing-profile')
        if not target.exists(): atomic_write(target, payload)
        os.chmod(target, 0o600)
        if 'fallback_password' in plan:
            update_fallback(system_root, plan['fallback_password'])
            result['fallback_updated'] = True
        result.update(ok=True, ssid=plan['ssid'], profile_filename=filename,
                      action='Wi-Fi profile prepared; normal boot must verify connectivity')
    except Exception as exc:
        # Fixed validation messages/types only; never echo payload or credentials.
        result['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    finally:
        try:
            if original is not None:
                atomic_write(boot / 'cmdline.txt', original)
                result['original_cmdline_restored'] = True
            else:
                result['original_cmdline_restored'] = False
                current = (boot / 'cmdline.txt').read_bytes()
                marker = (' ' + BOOT_ARGUMENTS).encode()
                if marker not in current: raise OSError('Cannot safely disarm recovery')
                atomic_write(boot / 'cmdline.txt', current.replace(marker, b'', 1))
                result['recovery_disarmed'] = True
            for suffix in ('.nmconnection', '.json', '.py'):
                (boot / (PREFIX + suffix)).unlink(missing_ok=True)
            if original is not None: (boot / (PREFIX + '.cmdline')).unlink(missing_ok=True)
            atomic_write(boot / (PREFIX + '.result.json'),
                         (json.dumps(result, ensure_ascii=False) + '\n').encode())
            if hasattr(os, 'sync'): os.sync()
        except OSError:
            result['cleanup_failed'] = True
    return result


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('root required')
    outcome = recover()
    print(json.dumps(outcome, ensure_ascii=False))
    # Reboot only after the one-time override was removed. Cleanup failure leaves
    # FailureAction=none, so corrupted boot media cannot cause a reboot loop.
    disarmed = outcome.get('original_cmdline_restored') or outcome.get('recovery_disarmed')
    raise SystemExit(0 if disarmed and not outcome.get('cleanup_failed') else 1)
