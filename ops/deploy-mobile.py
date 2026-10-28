#!/usr/bin/env python3
"""Install the reviewed mobile-r1 Dashboard only, after temporary sudo auth.

Fixed archive digest and destination; credentials are neither read nor printed.
The modular installer records releases/rollback in the existing deployment ledger.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import time
import urllib.request

ARCHIVE = Path('/tmp/pi-control-ssd-20261029-mobile-r1.tar.gz')
DESTINATION = Path('/opt/pi-control-bootstrap-20261029-mobile-r1')
SHA256 = '7d0127c10fbd0100c10832911af30c359d67d6111135e4a5bd8d21ca98e2f8c6'
RELEASES = {'dashboard': 'v1-ac307e1e21149e0c'}
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
    try:
        command('install', *arguments, '--modules', 'dashboard', '--apply', '--no-packages')
        ready()
        after = json.loads(METADATA.read_text())
        assert all(after[name]['release'] == release for name, release in RELEASES.items())
        assert all(after[name] == entry for name, entry in before.items() if name not in RELEASES)
        after_pids = subprocess.check_output(['runuser','-u','thinh','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','show','pi-control-media.service','pi-control-media-browser.service','pi-control-camera.service','-p','MainPID'],text=True)
        assert before_pids == after_pids, 'Media/Browser/Camera PID changed'
        print(json.dumps({'ok': True, 'media_browser_camera_pids_preserved': True, 'installed': RELEASES, 'other_module_metadata_unchanged': True}))
    except Exception:
        after = json.loads(METADATA.read_text())
        for name in reversed(tuple(RELEASES)):
            if after.get(name, {}).get('release') != before.get(name, {}).get('release'):
                command('rollback', *arguments, '--modules', name, '--apply')
        ready()
        raise


if __name__ == '__main__':
    main()
