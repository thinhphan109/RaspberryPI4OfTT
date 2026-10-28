"""Root, read-only collector. Only stdout contains the private archive; never log it."""
import hashlib
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tarfile
import time
from urllib.parse import quote

LIMIT = 128 * 1024 * 1024
PATHS = (
    '/etc/piwifi-web.env', '/etc/NetworkManager/system-connections',
    '/etc/adguardhome', '/etc/cloudflared', '/etc/bluetooth', '/var/lib/bluetooth',
    '/etc/systemd/system/piwifi-web.service', '/etc/systemd/system/piwifi-observer.service',
    '/etc/systemd/system/piwifi-guard.service', '/etc/systemd/system/piwifi-guard.timer',
    '/etc/systemd/system/adguardhome.service', '/etc/systemd/user/pi-media.service',
    '/etc/systemd/user/pi-media-browser.service', '/etc/NetworkManager/dispatcher.d/90-piwifi-dns',
    '/etc/systemd/user/pi-camera.service', '/home/thinh/.local/state/pi-camera',
    '/etc/sudoers.d/piwifi-web', '/etc/log2ram.conf',
    '/home/thinh/.config/adguardhome', '/home/thinh/.config/easyeffects',
    '/home/thinh/.local/state/pi-media', '/home/thinh/.local/state/wireplumber',
    '/var/lib/piwifi-observer/storage-writes.db',
    '/var/lib/piwifi-observer/system-events.json',
)


def collect(paths=PATHS, release=True):
    archive = io.BytesIO()
    manifest = dict(version=1, created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    files=[], missing=[], skipped=[])
    total = 0
    roots = list(map(Path, paths))
    if release:
        current = Path('/opt/piwifi-web').resolve(strict=True)
        if current.parent != Path('/opt/piwifi-releases'):
            raise RuntimeError('Unexpected managed release path')
        roots.append(current)
        manifest['release'] = str(current)
        for command, field in ((['uname', '-a'], 'kernel'),
                               (['dpkg-query', '-W', '-f=${Package}\t${Version}\n'], 'packages')):
            result = subprocess.run(command, capture_output=True, check=True, timeout=20)
            manifest[field] = result.stdout.decode()
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        seen = set()
        for root in roots:
            if not root.exists() and not root.is_symlink():
                manifest['missing'].append(str(root))
                continue
            # Do not follow symlinks inside selected configuration trees.
            candidates = [root]
            if root.is_dir() and not root.is_symlink():
                for parent, dirs, files in os.walk(root, followlinks=False):
                    for name in dirs[:]:
                        if (Path(parent) / name).is_symlink():
                            manifest['skipped'].append(str(Path(parent) / name))
                            dirs.remove(name)
                    candidates.extend(Path(parent) / name for name in files)
            for path in candidates:
                if str(path) in seen:
                    continue
                seen.add(str(path))
                st = path.lstat()
                if not stat.S_ISREG(st.st_mode):
                    if not stat.S_ISDIR(st.st_mode):
                        manifest['skipped'].append(str(path))
                    continue
                if st.st_size + total > LIMIT:
                    raise RuntimeError('Backup exceeds memory budget')
                if str(path).endswith('/storage-writes.db'):
                    # SQLite online backup includes committed WAL without stopping observer.
                    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as src:
                        with closing(sqlite3.connect(':memory:')) as dst:
                            src.backup(dst)
                            data = dst.serialize()
                            # The online backup is complete. Make its serialized image usable
                            # without WAL sidecars, including sqlite3_deserialize in recovery tests.
                            # https://www.sqlite.org/c3ref/deserialize.html
                            data = data[:18] + b'\x01\x01' + data[20:]
                else:
                    with path.open('rb') as stream:
                        data = stream.read(LIMIT - total + 1)
                total += len(data)
                if total > LIMIT:
                    raise RuntimeError('Backup exceeds memory budget')
                # Bluetooth addresses contain ':'; encode components for Windows recovery folders.
                name = '/'.join(quote(part, safe='') for part in path.parts if part != '/')
                item = tarfile.TarInfo(name)
                item.size, item.mode, item.uid, item.gid = len(data), stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid
                item.mtime = int(st.st_mtime)
                tar.addfile(item, io.BytesIO(data))
                manifest['files'].append(dict(path=name, original_path=path.as_posix(), sha256=hashlib.sha256(data).hexdigest(),
                                              size=len(data), mode=item.mode, uid=item.uid, gid=item.gid))
        data = json.dumps(manifest, ensure_ascii=False).encode()
        item = tarfile.TarInfo('manifest.json')
        item.size, item.mode = len(data), 0o600
        tar.addfile(item, io.BytesIO(data))
    return archive.getvalue()


if __name__ == '__main__':
    import sys
    if os.geteuid() != 0:
        raise SystemExit('Run collector with sudo')
    sys.stdout.buffer.write(collect())
