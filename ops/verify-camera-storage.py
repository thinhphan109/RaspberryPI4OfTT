"""Explicit on-Pi SSD mount/default check. Run with sudo, no active users.

Temporarily unmounts the selected filesystem, verifies fail-closed recording,
then mounts it through fstab in finally. Never formats or removes user data.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    assert os.geteuid()==0
    os.environ['PI_CAMERA_SOCKET']='/run/user/1000/pi-camera.sock'
    sys.path.insert(0,'/opt/piwifi-web')
    import camera
    call=camera.call
    before=call(dict(action='status'))
    assert not any(before[k] for k in ('recording','rendering','enabled','viewers')), 'Camera in use'
    mount=Path(before['storage_default'])
    expected=before['storage_uuid']
    assert expected and mount.is_mount() and not mount.is_symlink()
    def run(*args):return subprocess.check_output(args,text=True).strip()
    assert run('findmnt','-rn','--target',str(mount),'-o','UUID')==expected
    try:
        subprocess.run(['umount',str(mount)],check=True,timeout=15)
        # Desktop automount directories may disappear on unmount; managed /mnt stays.
        underlying=set(mount.iterdir()) if mount.exists() else set()
        call(dict(action='power',enabled=True))
        for _ in range(30):
            if call(dict(action='status'))['available']:break
            time.sleep(.2)
        else:raise AssertionError('No webcam frame')
        try:
            call(dict(action='start',mode='interval',interval=2))
        except ValueError as exc:
            assert 'SSD' in str(exc),str(exc)
        else:raise AssertionError('Recording unexpectedly started without preferred SSD')
        current=call(dict(action='status'))
        assert current['storage_default'] is None and not current['recording']
        assert (set(mount.iterdir()) if mount.exists() else set())==underlying,'Underlying SD directory changed'
        print(json.dumps(dict(check='unmounted preferred SSD blocks recording; no SD fallback',ok=True)))
    finally:
        # The diagnostic never leaves the filesystem intentionally unmounted.
        if not mount.is_mount():
            mount.mkdir(parents=True,exist_ok=True)
            subprocess.run(['mount',str(mount)],check=True,timeout=15)
        call(dict(action='power',enabled=False))
    assert run('findmnt','-rn','--target',str(mount),'-o','UUID')==expected
    for _ in range(18):
        current=call(dict(action='status'))
        if current['storage_default']==str(mount):break
        time.sleep(1)
    else:raise AssertionError('SSD not rediscovered')
    print(json.dumps(dict(check='fstab mount and preferred UUID rediscovery',ok=True,mount=str(mount))))


if __name__=='__main__':main()
