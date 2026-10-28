#!/usr/bin/python3 -B
"""Stage verified source on the prepared SSD without installing any service."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT_UUID='98a7c93a-53ab-4f91-b51e-0bbccfc1fff2'
DATA_UUID='056d5180-c190-4d50-9e2e-7cd4fcc81a91'
DEVICE='/dev/disk/by-id/usb-JMicron_JMicron_1234A3-0:0'


def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=30).stdout.strip()


def stage(kit):
    if os.geteuid()!=0:raise ValueError('Run as root from the SD OS')
    if run(['findmnt','-n','-o','SOURCE','/'])!='/dev/mmcblk0p2':raise ValueError('Expected SD root')
    for part,expected in (('part2',ROOT_UUID),('part3',DATA_UUID)):
        if run(['/usr/sbin/blkid','-s','UUID','-o','value',DEVICE+'-'+part])!=expected:raise ValueError('Wrong prepared SSD')
    sys.path.insert(0,str(kit));from bootstrap import verify_bundle
    manifest,_=verify_bundle(kit)
    base=Path('/run/pi-ssd-offline-stage');base.mkdir(mode=0o700,exist_ok=False)
    run(['mount',DEVICE+'-part2',str(base)])
    data=None
    try:
        fstab=(base/'etc/fstab').read_text()
        if 'UUID='+DATA_UUID+' /srv/pi-control' not in fstab:raise ValueError('Missing data mount configuration')
        target=base/'opt/pi-control-bootstrap'
        if target.exists() or target.is_symlink():raise ValueError('Staging already exists; inspect before replacing')
        shutil.copytree(kit,target,copy_function=shutil.copyfile)
        # Files created by this root process, not preserved user ownership from /tmp.
        for path in target.rglob('*'):
            if path.is_symlink():raise ValueError('Unexpected source link')
            path.chmod(0o755 if path.is_dir() else 0o644)
        target.chmod(0o755);verify_bundle(target)
        data=base/'srv/pi-control'
        if data.is_symlink():raise ValueError('Unsafe data mountpoint')
        run(['mount',DEVICE+'-part3',str(data)])
        volume=dict(schema=1,root_uuid=ROOT_UUID,data_uuid=DATA_UUID,model='PM991 NVMe Samsung 128GB',purpose='Pi Control data')
        marker=data/'.pi-control-volume.json'
        with marker.open('x',encoding='utf-8') as stream:
            os.chmod(marker,0o600);json.dump(volume,stream);stream.flush();os.fsync(stream.fileno())
        assert json.loads(marker.read_text())==volume
        run(['sync','-f',str(marker)])
        result=dict(source_staged='/opt/pi-control-bootstrap',modules=len(manifest['modules']),files=len(manifest['files']),data_write_fsync_readback=True,
                    root_uuid=ROOT_UUID,data_uuid=DATA_UUID,services_installed=False,ssd_boot_pending=True)
        run(['sync','-f',str(target)])
        return result
    finally:
        if data is not None and os.path.ismount(data):run(['umount',str(data)])
        run(['umount',str(base)])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path);args=parser.parse_args()
    print(json.dumps(stage(args.kit.resolve()),indent=2))
