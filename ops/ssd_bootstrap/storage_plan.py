#!/usr/bin/env python3
"""Read-only layout proposal. Never runs parted, mkfs, dd or a mount command."""
import argparse
import json
import re
import subprocess

GIB=1024**3


def propose(device):
    if not re.fullmatch(r'/dev/sd[a-z]+',device):raise ValueError('Select a whole USB disk such as /dev/sda, after checking model and serial')
    output=subprocess.run(['lsblk','--tree','-b','--json','-o','PATH,TYPE,TRAN,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS',device],capture_output=True,text=True,check=True,timeout=10)
    disks=json.loads(output.stdout)['blockdevices']
    if len(disks)!=1:raise ValueError('Ambiguous disk')
    disk=disks[0]
    if disk['type']!='disk' or disk.get('tran')!='usb' or not 120_000_000_000<=int(disk['size'])<=130_000_000_000:raise ValueError('Expected the 128 GB USB SSD')
    total=int(disk['size']);unused=total-(512*1024**2+40*GIB+68*GIB)
    return {'read_only':True,'disk':disk,'proposed':{'boot_MiB':512,'root_GiB':40,'data_GiB':68,'unallocated_GiB':round(unused/GIB,2)},
            'next':'After imaging, inspect the actual partition table while booted from SD; prepare layout before first SSD boot. Do not assume partition offsets.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--device',required=True)
    print(json.dumps(propose(parser.parse_args().device),indent=2))
