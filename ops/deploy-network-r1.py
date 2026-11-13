#!/usr/bin/env python3
"""Install the reviewed network-r1 Wi-Fi guard and Dashboard, after temporary sudo auth.

Fixed archive digest and destination; credentials are neither read nor printed.
The modular installer records releases/rollback in the existing deployment ledger.
"""
import hashlib
import fcntl
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import time
import urllib.request

ARCHIVE = Path('/tmp/pi-control-ssd-20261102-network-r1.tar.gz')
DESTINATION = Path('/opt/pi-control-bootstrap-20261102-network-r1')
SHA256 = 'fc6e03abb1f94fe6148d46a98ab45814022e5fc5df404b1948cefcc52b4ec723'
RELEASES = {'network': 'v1-ffcc192dfc5c1572', 'dashboard': 'v1-c0cdd47f6371c7df'}
METADATA = Path('/var/lib/pi-control/control/modules.json')


def command(*args):
    subprocess.run(['/usr/bin/python3', '-B', str(DESTINATION/'bootstrap.py'), *args], check=True)


def ready():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(20):
        try:
            with opener.open('http://127.0.0.1:18765/login', timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError('Dashboard HTTP /login did not return 200 after restart')


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run with temporarily authorized sudo')
    if ARCHIVE.is_symlink() or not ARCHIVE.is_file() or ARCHIVE.stat().st_size > 60*1024*1024:
        raise RuntimeError('Unexpected archive')
    raw = ARCHIVE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise RuntimeError('Archive checksum mismatch')
    if DESTINATION.exists() or DESTINATION.is_symlink():
        raise RuntimeError('Destination already exists; inspect the previous attempt first')
    # Parse the verified bytes rather than reopening a mutable upload path.
    import io
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        seen = set()
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or member.name in seen or member.size > 100*1024*1024):
                raise RuntimeError('Unsafe archive member')
            seen.add(member.name)
        DESTINATION.mkdir(mode=0o755)
        archive.extractall(DESTINATION, filter='data')
    for path in [DESTINATION, *DESTINATION.rglob('*')]:
        os.chown(path, 0, 0)
        path.chmod(0o755 if path.is_dir() else 0o644)
    command('verify')
    before = json.loads(METADATA.read_text())
    before_pids = subprocess.check_output(['runuser','-u','thinh','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','show','pi-control-media.service','pi-control-media-browser.service','pi-control-camera.service','-p','MainPID'],text=True)
    arguments = ('--config', '/etc/pi-control/runtime.json')
    profiles = Path('/etc/NetworkManager/system-connections')
    before_profiles = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in profiles.iterdir() if p.is_file()}
    raw = subprocess.check_output(['nmcli','-g','GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS','device','show','wlan0'],text=True).splitlines()
    assert int(raw[0].split()[0]) == 100 and ipaddress.ip_interface(raw[2]).version == 4, 'Require working Wi-Fi before deployment'
    with open('/run/piwifi-network.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            subprocess.run(['systemctl','stop','pi-control-network-guard.timer','pi-control-network-guard.service'],check=True,timeout=15)
            command('install', *arguments, '--modules', 'network,dashboard', '--apply', '--no-packages')
            ready()
            after = json.loads(METADATA.read_text())
            assert all(after[name]['release'] == release for name, release in RELEASES.items())
            assert all(after[name] == entry for name, entry in before.items() if name not in RELEASES)
            after_profiles = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in profiles.iterdir() if p.is_file()}
            assert before_profiles == after_profiles, 'Network profile content changed'
            after_pids = subprocess.check_output(['runuser','-u','thinh','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','show','pi-control-media.service','pi-control-media-browser.service','pi-control-camera.service','-p','MainPID'],text=True)
            assert before_pids == after_pids, 'Media/Browser/Camera PID changed'
        except Exception:
            after = json.loads(METADATA.read_text())
            for name in reversed(tuple(RELEASES)):
                if after.get(name, {}).get('release') != before.get(name, {}).get('release'):
                    command('rollback', *arguments, '--modules', name, '--apply')
            ready()
            raise
        finally:
            subprocess.run(['systemctl','start','pi-control-network-guard.timer'],check=True,timeout=15)
            fcntl.flock(lock, fcntl.LOCK_UN)
    subprocess.run(['systemctl','start','pi-control-network-guard.service'],check=True,timeout=30)
    state = json.loads(Path('/run/piwifi-guard.json').read_text())
    assert state.get('state') == 'preserved' and time.time()-state.get('timestamp',0) < 10, 'Guard did not preserve working Wi-Fi'
    print(json.dumps({'ok': True, 'media_browser_camera_pids_preserved': True, 'installed': RELEASES,
                      'other_module_metadata_unchanged': True, 'network_profiles_unchanged': True, 'guard': state}))



if __name__ == '__main__':
    main()
