"""Root-owned settings for fresh modular installs; absent means legacy layout.

Never accepts a browser-supplied path or a sudo-preserved environment override.
"""
import json
import os
from pathlib import Path
import re
import stat

CONFIG_FILE = Path('/etc/pi-control/runtime.json')
UNIT_MAP = {
    'piwifi-web':'pi-control-dashboard', 'piwifi-observer':'pi-control-observer',
    'piwifi-guard':'pi-control-network-guard', 'piwifi-guard.timer':'pi-control-network-guard.timer',
    'pi-media':'pi-control-media', 'pi-media-browser':'pi-control-media-browser',
    'pi-camera':'pi-control-camera', 'pi-audio':'pi-control-audio',
}


def load(path=CONFIG_FILE, require_root=True):
    try:info=path.lstat()
    except FileNotFoundError:return None
    if not stat.S_ISREG(info.st_mode) or info.st_size>16384 or info.st_mode & 0o022 or require_root and info.st_uid!=0:
        raise ValueError('Unsafe Pi Control runtime configuration')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or value.get('schema')!=1:raise ValueError('Invalid runtime schema')
    user=value.get('desktop_user','')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',user):raise ValueError('Invalid desktop user')
    if type(value.get('desktop_uid')) is not int or not 1000<=value['desktop_uid']<2**31:raise ValueError('Invalid desktop UID')
    if value.get('desktop_home')!='/home/'+user:raise ValueError('Invalid desktop home')
    if not re.fullmatch(r'[a-f0-9]{32}',value.get('generation','')):raise ValueError('Invalid generation')
    if value.get('data_mount')!='/srv/pi-control':raise ValueError('Invalid data mount')
    if not re.fullmatch(r'[a-fA-F0-9-]{8,64}',value.get('data_uuid','')):raise ValueError('Invalid data UUID')
    if not re.fullmatch(r'[a-fA-F0-9-]{8,64}',value.get('root_uuid','')):raise ValueError('Invalid root UUID')
    device=value.get('camera_device','auto')
    if device!='auto' and not re.fullmatch(r'/dev/v4l/by-id/[A-Za-z0-9_.:-]+-video-index0',device):raise ValueError('Invalid camera device')
    return value


CONFIG=load()


def modular():return CONFIG is not None


def unit(name):
    if not modular():return name
    suffix='.service' if name.endswith('.service') else ''
    base=name[:-8] if suffix else name
    return UNIT_MAP.get(base,base)+suffix


def location(name, legacy):
    if not modular():return Path(legacy)
    paths={
        'events':'/var/lib/pi-control/control',
        'observer_state':'/var/lib/pi-control/observer',
        'observer_run':'/run/pi-control-observer',
        'camera_state':'/var/lib/pi-control/camera',
        'media_state':'/var/lib/pi-control/media',
        'history':'/var/lib/pi-control/control/deploy-history.json',
        'adguard_credentials':CONFIG['desktop_home']+'/.config/adguardhome/credentials.json',
    }
    if name not in paths:raise ValueError('Unknown runtime location')
    return Path(paths[name])


def desktop_runtime():
    return Path('/run/user')/str(CONFIG['desktop_uid'] if modular() else os.getuid())
