#!/usr/bin/python3 -B
"""One-time offline preparation of the newly imaged, specifically identified SSD.

Default prints a read-only plan. --apply requires the old Pi OS to run from SD.
No SD changes, bootloader changes, old-system backup or credential transfer.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import uuid

DEVICE='/dev/disk/by-id/usb-JMicron_JMicron_1234A3-0:0'
EXPECTED_ID='0x9586d7bf'
CAPACITY=128035676160
SECTOR=512
ROOT_START=1064960
ROOT_SECTORS=40*1024**3//SECTOR
DATA_SECTORS=68*1024**3//SECTOR


def run(args,allowed=(0,),timeout=120):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode not in allowed:raise RuntimeError('Failed: '+args[0]+': '+result.stderr[:500])
    return result.stdout.strip()


def geometry(table,capacity):
    if capacity!=CAPACITY:raise ValueError('Wrong SSD capacity')
    if table.get('label')!='dos' or table.get('id')!=EXPECTED_ID or table.get('sectorsize')!=SECTOR:raise ValueError('Unexpected image partition table')
    parts=table.get('partitions',[])
    if len(parts)!=2:raise ValueError('Expected the untouched 2-partition image; do not repeat mkfs')
    if (parts[0]['start'],parts[0]['size'],parts[0]['type'])!=(16384,1048576,'c'):raise ValueError('Unexpected boot partition')
    if (parts[1]['start'],parts[1]['size'],parts[1]['type'])!=(ROOT_START,12107776,'83'):raise ValueError('Unexpected root partition')
    data_start=ROOT_START+ROOT_SECTORS
    data_end=data_start+DATA_SECTORS-1
    if data_end>=capacity//SECTOR:raise ValueError('Layout exceeds device')
    return dict(root_start=ROOT_START,root_sectors=ROOT_SECTORS,root_end=data_start-1,
                data_start=data_start,data_sectors=DATA_SECTORS,data_end=data_end,
                unallocated_bytes=capacity-(data_end+1)*SECTOR)


def identity(smartctl):
    root=run(['findmnt','-n','-o','SOURCE','/'])
    boot=run(['findmnt','-n','-o','SOURCE','/boot/firmware'])
    if root!='/dev/mmcblk0p2' or boot!='/dev/mmcblk0p1':raise ValueError('Run only from the existing SD OS, with SD boot partition')
    disk=json.loads(run(['lsblk','--tree','-b','-J','-o','PATH,TYPE,TRAN,SIZE,SERIAL,MOUNTPOINTS',DEVICE]))['blockdevices']
    if len(disk)!=1:raise ValueError('Ambiguous device')
    disk=disk[0]
    if disk.get('type')!='disk' or disk.get('tran')!='usb' or disk.get('serial')!='1234A3' or disk.get('size')!=CAPACITY:raise ValueError('Not the approved JMicron USB SSD')
    smart=json.loads(run([str(smartctl),'-i','-j','-d','sntjmicron',DEVICE]))
    if smart.get('model_name')!='PM991 NVMe Samsung 128GB' or smart.get('serial_number')!='S50CNE1MB11742':raise ValueError('Wrong physical NVMe SSD')
    table=json.loads(run(['/usr/sbin/sfdisk','--json',DEVICE]))['partitiontable']
    return disk,geometry(table,disk['size'])


def cmdline_text(text):
    tokens=text.split()
    if tokens.count('resize')!=1 or [t for t in tokens if t.startswith('root=')]!=['root=PARTUUID=9586d7bf-02']:raise ValueError('Unexpected boot command line')
    return ' '.join(t for t in tokens if t!='resize')+'\n'


def fstab_text(text,data_uuid):
    if not re.fullmatch(r'[a-f0-9-]{36}',data_uuid):raise ValueError('Invalid data UUID')
    roots={}
    for line in text.splitlines():
        fields=line.split()
        if not fields or fields[0].startswith('#'):continue
        if len(fields)<4:raise ValueError('Unexpected fstab line')
        roots[fields[1]]=fields[0]
    if roots.get('/')!='PARTUUID=9586d7bf-02' or roots.get('/boot/firmware')!='PARTUUID=9586d7bf-01':raise ValueError('Image fstab identity mismatch')
    if '/srv/pi-control' in roots:raise ValueError('Data mount already configured')
    return text.rstrip()+f'\nUUID={data_uuid} /srv/pi-control ext4 defaults,noatime,nofail,x-systemd.device-timeout=5s 0 2\n'


def replace_file(path,value):
    if path.is_symlink() or not path.is_file():raise ValueError('Unexpected image file')
    info=path.stat();temporary=path.with_name(path.name+'.pi-control-new')
    with temporary.open('xb') as stream:
        stream.write(value.encode());stream.flush();os.fsync(stream.fileno())
    os.chmod(temporary,info.st_mode&0o777);os.chown(temporary,info.st_uid,info.st_gid)
    os.replace(temporary,path)
    run(['sync','-f',str(path)])


@contextmanager
def mounted(device,path,options):
    path.mkdir(mode=0o700,parents=True,exist_ok=False)
    run(['mount','-o',options,device,str(path)])
    try:yield path
    finally:run(['umount',str(path)])


def prepare(smartctl,work,apply=False):
    if os.geteuid()!=0:raise ValueError('Requires root to identify and inspect the SSD')
    if not work.is_dir() or work.is_symlink() or not str(work).startswith('/tmp/pi-ssd-layout.'):raise ValueError('Use the exact isolated staging directory')
    disk,layout=identity(smartctl)
    plan=dict(device=DEVICE,physical_model='PM991 NVMe Samsung 128GB',serial='S50CNE1MB11742',capacity_bytes=CAPACITY,
              partition_table_id=EXPECTED_ID,layout=layout,changes_sd=False,changes_eeprom=False)
    if not apply:return plan
    # Unmount only this disk; do not force an unmount with open handles.
    for part in disk.get('children',[]):
        for mount in part.get('mountpoints') or []:
            if mount:run(['umount',mount])
    _,same=identity(smartctl)
    if same!=layout:raise ValueError('Disk changed')
    if any(mount for p in json.loads(run(['lsblk','--tree','-J','-o','MOUNTPOINTS',DEVICE]))['blockdevices'][0].get('children',[]) for mount in p.get('mountpoints') or []):
        raise ValueError('SSD still mounted')
    # Validate the complete intended edits before changing a partition boundary.
    with mounted(DEVICE+'-part1',work/'pre-boot','ro') as boot:
        commandline=(boot/'cmdline.txt').read_text();new_commandline=cmdline_text(commandline)
        provisioning={name:hashlib.sha256((boot/name).read_bytes()).hexdigest() for name in ('user-data','network-config','meta-data') if (boot/name).is_file()}
    root_uuid=str(uuid.uuid4());data_uuid=str(uuid.uuid4());fat_id=secrets.token_hex(4)
    with mounted(DEVICE+'-part2',work/'pre-root','ro,noload') as root:
        fstab=(root/'etc/fstab').read_text();new_fstab=fstab_text(fstab,data_uuid)
        if (root/'etc/pi-control/runtime.json').exists():raise ValueError('Already provisioned system')
        if 'VERSION_CODENAME=trixie' not in (root/'etc/os-release').read_text():raise ValueError('Unexpected OS image')
    run(['/usr/sbin/e2fsck','-f','-p',DEVICE+'-part2'],allowed=(0,1),timeout=180)
    plan.update(root_uuid=root_uuid,data_uuid=data_uuid,boot_volume_id=fat_id,provisioning_preserved=sorted(provisioning))
    # Metadata only; does not contain credentials or an OS/data backup.
    (work/'planned-layout.json').write_text(json.dumps(plan,indent=2));os.chmod(work/'planned-layout.json',0o600)
    run(['/usr/sbin/parted','-s',DEVICE,'unit','s','resizepart','2',str(layout['root_end'])+'s'])
    run(['/usr/sbin/parted','-s',DEVICE,'unit','s','mkpart','primary','ext4',str(layout['data_start'])+'s',str(layout['data_end'])+'s'])
    run(['udevadm','settle'])
    table=json.loads(run(['/usr/sbin/sfdisk','--json',DEVICE]))['partitiontable']
    if table['id']!=EXPECTED_ID or [(p['start'],p['size']) for p in table['partitions']]!=[(16384,1048576),(ROOT_START,ROOT_SECTORS),(layout['data_start'],DATA_SECTORS)]:raise ValueError('Partition verification failed')
    run(['/usr/sbin/resize2fs',DEVICE+'-part2'],timeout=300)
    run(['/usr/sbin/tune2fs','-U',root_uuid,DEVICE+'-part2'],timeout=180)
    run(['/usr/sbin/e2fsck','-f','-p',DEVICE+'-part2'],allowed=(0,1),timeout=180)
    run(['/usr/sbin/mkfs.ext4','-U',data_uuid,'-L','PiControlData','-m','1','-E','nodiscard',DEVICE+'-part3'],timeout=180)
    run(['/usr/sbin/fatlabel','--volume-id',DEVICE+'-part1',fat_id])
    with mounted(DEVICE+'-part1',work/'edit-boot','rw') as boot:
        if (boot/'cmdline.txt').read_text()!=commandline:raise ValueError('Boot configuration changed during preparation')
        for name,digest in provisioning.items():
            if hashlib.sha256((boot/name).read_bytes()).hexdigest()!=digest:raise ValueError('Imager provisioning changed')
        replace_file(boot/'cmdline.txt',new_commandline)
    with mounted(DEVICE+'-part2',work/'edit-root','rw') as root:
        if (root/'etc/fstab').read_text()!=fstab:raise ValueError('fstab changed during preparation')
        replace_file(root/'etc/fstab',new_fstab)
        data=root/'srv/pi-control'
        if data.is_symlink():raise ValueError('Unsafe data mountpoint')
        data.mkdir(parents=True,exist_ok=True,mode=0o755)
        # Do not create desktop accounts, keys or credentials; Imager/cloud-init owns first boot.
    run(['sync'])
    for part,expected in (('part2',root_uuid),('part3',data_uuid)):
        if run(['/usr/sbin/blkid','-s','UUID','-o','value',DEVICE+'-'+part])!=expected:raise ValueError('Filesystem UUID verification failed')
    if run(['findmnt','-n','-o','SOURCE','/'])!='/dev/mmcblk0p2':raise ValueError('Unexpected active root')
    plan.update(applied=True,finished_at=int(time.time()),first_ssd_boot_pending=True)
    (work/'finished-layout.json').write_text(json.dumps(plan,indent=2));os.chmod(work/'finished-layout.json',0o600)
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smartctl',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.smartctl,args.work,args.apply),indent=2))
