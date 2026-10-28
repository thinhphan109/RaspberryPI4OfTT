#!/usr/bin/python3 -B
"""Fresh-SSD modular installer. Default commands only verify/plan.

No disk-formatting, bootloader update, Wi-Fi transition or old-system backup.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import uuid
sys.dont_write_bytecode=True

BASE=Path(__file__).resolve().parent
MANAGED=('network','observer','audio','media','render','camera','dashboard','dns')


def command(args,timeout=120):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()


def safe_relative(value):
    path=PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in ('..','.') for p in path.parts) or '\\' in value:raise ValueError('Unsafe package path')
    return path


def verify_bundle(base=BASE):
    manifest_path=base/'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>2*1024*1024:raise ValueError('Invalid manifest')
    raw=manifest_path.read_bytes()
    expected=(base/'manifest.sha256').read_text().strip()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Manifest checksum mismatch')
    manifest=json.loads(raw)
    if manifest.get('schema')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Unsupported bundle')
    for name,digest in manifest['files'].items():
        path=base.joinpath(*safe_relative(name).parts)
        if not re.fullmatch('[a-f0-9]{64}',digest) or path.is_symlink() or not path.is_file():raise ValueError('Invalid package member')
        if path.resolve().is_relative_to(base.resolve()) is False:raise ValueError('Package path escapes bundle')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Package checksum mismatch: '+name)
    if any(p.is_symlink() for p in base.rglob('*')):raise ValueError('Bundle symlinks are not allowed')
    actual={str(p.relative_to(base)).replace('\\','/') for p in base.rglob('*') if p.is_file() and p.relative_to(base).as_posix() not in ('manifest.json','manifest.sha256')}
    if actual!=set(manifest['files']):raise ValueError('Unlisted or missing package files')
    catalog=json.loads((base/'catalog.json').read_text())
    for name,spec in catalog['modules'].items():
        if name in MANAGED and name not in manifest['modules']:raise ValueError('Missing managed module')
        if any(dep not in catalog['modules'] for dep in spec['requires']):raise ValueError('Unknown dependency')
    for name,spec in manifest['modules'].items():
        if name not in MANAGED or not re.fullmatch('v1-[a-f0-9]{16}',spec.get('release','')):raise ValueError('Invalid module release')
        entries={key.removeprefix('files/'+name+'/'):value for key,value in manifest['files'].items() if key.startswith('files/'+name+'/')}
        expected=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
        if expected!=spec.get('source_hash'):raise ValueError('Module hash mismatch')
    return manifest,catalog


def resolve_modules(requested,catalog,installed=None):
    installed=installed or {};result=[];visiting=set()
    def visit(name):
        if name not in MANAGED:raise ValueError('Module requires separate configuration/deploy: '+name)
        if name in result:return
        if name in visiting:raise ValueError('Dependency cycle')
        visiting.add(name)
        for dependency in catalog['modules'][name]['requires']:
            if dependency not in installed:visit(dependency)
        visiting.remove(name);result.append(name)
    for name in requested:visit(name)
    return result


def mount_info(target):
    rows=json.loads(command(['findmnt','--json','-o','TARGET,SOURCE,FSTYPE,UUID','--target',target]))['filesystems']
    if len(rows)!=1 or rows[0]['target']!=target:raise ValueError('Missing exact mount: '+target)
    return rows[0]


def discover(user):
    import pwd
    account=pwd.getpwnam(user)
    root=mount_info('/');data=mount_info('/srv/pi-control')
    previous=Path('/etc/pi-control/runtime.json')
    generation=json.loads(previous.read_text())['generation'] if previous.exists() else uuid.uuid4().hex
    return dict(schema=1,desktop_user=user,desktop_uid=account.pw_uid,desktop_home=account.pw_dir,generation=generation,
                root_uuid=root['uuid'],data_mount='/srv/pi-control',data_uuid=data['uuid'],camera_device='auto')


def validate_host(config):
    # Same schema validation as the installed runtime, without accepting sudo env overrides.
    required=('desktop_user','desktop_uid','desktop_home','generation','root_uuid','data_mount','data_uuid')
    if not isinstance(config,dict) or config.get('schema')!=1 or any(k not in config for k in required):raise ValueError('Incomplete host configuration')
    if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}',config['desktop_user']) or config['desktop_home']!='/home/'+config['desktop_user']:raise ValueError('Invalid desktop identity')
    if type(config['desktop_uid']) is not int or not 1000<=config['desktop_uid']<2**31:raise ValueError('Invalid desktop UID')
    if not re.fullmatch('[a-f0-9]{32}',config['generation']):raise ValueError('Invalid OS generation')
    if config['data_mount']!='/srv/pi-control' or any(not re.fullmatch('[a-fA-F0-9-]{8,64}',config[k]) for k in ('root_uuid','data_uuid')):raise ValueError('Invalid storage identity')
    if config['root_uuid']==config['data_uuid']:raise ValueError('OS and data must be distinct filesystems')
    device=config.get('camera_device','auto')
    if device!='auto' and not re.fullmatch(r'/dev/v4l/by-id/[A-Za-z0-9_.:-]+-video-index0',device):raise ValueError('Invalid camera device')
    return config


def legacy_exists():return Path('/opt/piwifi-web').exists() or Path('/etc/piwifi-web.env').exists()


def preflight(config,root=Path('/')):
    validate_host(config)
    if root!=Path('/'):
        if not root.is_absolute() or root.is_symlink():raise ValueError('Sandbox root must be an absolute real directory')
        return {'sandbox':True,'mutates_host':False}
    if os.geteuid()!=0:raise ValueError('Apply requires sudo on the new SSD OS')
    if legacy_exists():raise ValueError('Legacy system detected; do not install over the SD system')
    if os.uname().machine!='aarch64':raise ValueError('Expected aarch64 Raspberry Pi OS')
    current=mount_info('/');data=mount_info(config['data_mount'])
    if current['fstype']!='ext4' or data['fstype']!='ext4':raise ValueError('Expected ext4 OS/data')
    if current['uuid']!=config['root_uuid'] or data['uuid']!=config['data_uuid']:raise ValueError('Mounted UUID does not match host plan')
    if current['source'].startswith('/dev/mmcblk') or current['source']==data['source']:raise ValueError('Refusing SD/root data fallback')
    if not re.fullmatch(r'/dev/(?:sd[a-z]+\d+|nvme\d+n\d+p\d+)',current['source']):raise ValueError('Unsupported OS device')
    disks=json.loads(command(['lsblk','--tree','--json','-b','-o','PATH,TYPE,PKNAME,SIZE,TRAN']))['blockdevices']
    flattened=[]
    def walk(rows,parent=None):
        for row in rows:
            flattened.append((row,parent));walk(row.get('children',[]),row)
    walk(disks)
    parent_root=next((parent for row,parent in flattened if row['path']==current['source']),None)
    parent_data=next((parent for row,parent in flattened if row['path']==data['source']),None)
    if not parent_root or not parent_data or parent_root['path']!=parent_data['path']:raise ValueError('OS and data must belong to the same approved SSD')
    if parent_root.get('tran')!='usb' or not 120_000_000_000<=int(parent_root['size'])<=130_000_000_000:raise ValueError('Expected the 128 GB USB SSD; review physical identity first')
    import pwd
    account=pwd.getpwnam(config['desktop_user'])
    if (account.pw_uid,account.pw_dir)!=(config['desktop_uid'],config['desktop_home']):raise ValueError('Desktop account mismatch')
    return {'sandbox':False,'root':current['source'],'data':data['source'],'generation':config['generation']}


def destination(root,path):
    relative=PurePosixPath(path).relative_to('/')
    target=root.joinpath(*relative.parts)
    current=root
    for part in relative.parts:
        current=current/part
        if current.is_symlink():raise ValueError('Unexpected destination symlink: '+str(current))
    return target


def write(root,path,value,mode=0o644,uid=None):
    target=destination(root,path);target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_symlink():raise ValueError('Unsafe destination')
    raw=value.encode() if isinstance(value,str) else value
    temporary=target.with_name(target.name+'.new')
    if temporary.exists() or temporary.is_symlink():raise ValueError('Pending installer file requires review')
    with temporary.open('xb') as stream:
        os.chmod(temporary,mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if uid is not None and root==Path('/'):os.chown(temporary,uid,-1)
    os.replace(temporary,target)
    descriptor=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    return target


def user_command(config,args):
    uid=config['desktop_uid']
    return command(['runuser','-u',config['desktop_user'],'--','env',f'XDG_RUNTIME_DIR=/run/user/{uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus',*args])


def units(module,config):
    user=config['desktop_user'];uid=config['desktop_uid'];base=f'/opt/pi-control/{module}/current'
    common='Restart=on-failure\nRestartSec=3\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n'
    install='\n[Install]\nWantedBy=multi-user.target\n'
    if module=='dashboard':return {'pi-control-dashboard.service':f'[Unit]\nDescription=Pi Control Dashboard and API\nAfter=network.target\n[Service]\nUser={user}\nGroup={user}\nWorkingDirectory={base}\nEnvironmentFile=/etc/pi-control/dashboard/auth.env\nExecStart=/usr/bin/gunicorn --workers 1 --worker-class gthread --threads 4 --worker-connections 32 --worker-tmp-dir /dev/shm --bind 0.0.0.0:18765 --error-logfile - app:app\nPrivateTmp=true\n{common}'+install+'Alias=piwifi-web.service\n'}
    if module=='network':return {
        'pi-control-network-guard.service':'[Unit]\nDescription=Pi Control Wi-Fi recovery guard\nAfter=NetworkManager.service\nRequires=NetworkManager.service\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/piwifi-guard\nTimeoutStartSec=180\n[Install]\nAlias=piwifi-guard.service\n',
        'pi-control-network-guard.timer':'[Unit]\nDescription=Pi Control network recovery schedule\n[Timer]\nOnBootSec=60\nOnUnitInactiveSec=30\nUnit=pi-control-network-guard.service\n[Install]\nWantedBy=timers.target\nAlias=piwifi-guard.timer\n'}
    if module=='observer':return {'pi-control-observer.service':f'[Unit]\nDescription=Pi Control observer and selected event journal\nAfter=NetworkManager.service\n[Service]\nUser={user}\nGroup={user}\nWorkingDirectory={base}\nExecStart=/usr/bin/python3 -B {base}/observer.py\nStateDirectory=pi-control/observer\nStateDirectoryMode=0700\nRuntimeDirectory=pi-control-observer\nRuntimeDirectoryMode=0755\nProtectSystem=strict\nProtectHome=true\nPrivateTmp=true\nBindReadOnlyPaths=-/run/user/{uid}:/run/piwifi-camera-runtime\nEnvironment=PIWIFI_CAMERA_RUNTIME=/run/piwifi-camera-runtime\n{common}'+install+'Alias=piwifi-observer.service\n'}
    user_install='\n[Install]\nWantedBy=default.target\n'
    if module=='audio':return {'pi-control-audio.service':f'[Unit]\nDescription=Pi Control Audio and Bluetooth\nAfter=pipewire.service wireplumber.service\n[Service]\nWorkingDirectory={base}\nExecStart=/usr/bin/python3 -B {base}/audio_agent.py\nUMask=0077\nNoNewPrivileges=true\n{common}'+user_install}
    if module=='media':return {
        'pi-control-media.service':f'[Unit]\nDescription=Pi Control Media agent\nAfter=pipewire.service\n[Service]\nWorkingDirectory={base}\nExecStart=/usr/bin/python3 -B {base}/media_agent.py\nUMask=0077\n{common}'+user_install+'Alias=pi-media.service\n',
        'pi-control-media-browser.service':'[Unit]\nDescription=Pi Control dedicated Media browser\nAfter=graphical-session.target\n[Service]\nExecStart=/usr/lib/chromium/chromium --ozone-platform=wayland --password-store=basic --disable-renderer-backgrounding --user-data-dir=%h/.local/share/pi-control/chromium --disk-cache-dir=%t/pi-control-browser-cache --disk-cache-size=134217728 --remote-debugging-address=127.0.0.1 --remote-debugging-port=18769 --no-first-run --no-default-browser-check --autoplay-policy=no-user-gesture-required --app=about:blank\nRestart=no\n[Install]\nAlias=pi-media-browser.service\n'}
    if module=='camera':return {'pi-control-camera.service':f'[Unit]\nDescription=Pi Control Camera agent\n[Service]\nWorkingDirectory={base}\nExecStart=/usr/bin/python3 -B {base}/camera_agent.py\nMemoryMax=512M\nCPUQuota=100%\nUMask=0077\nNoNewPrivileges=true\nTimeoutStopSec=8\nKillMode=control-group\n{common}'+user_install+'Alias=pi-camera.service\n'}
    if module=='render':return {'pi-control-camera-render@.service':f'[Unit]\nDescription=Pi Control render job %i\n[Service]\nType=oneshot\nWorkingDirectory={base}\nExecStart=/usr/bin/python3 -B {base}/camera_renderer.py --job-id %i\nMemoryMax=768M\nCPUQuota=100%\nNice=10\nUMask=0077\nNoNewPrivileges=true\nTimeoutStartSec=1830\n'}
    if module=='dns':return {'adguardhome.service':'[Unit]\nDescription=AdGuard Home DNS\nAfter=network.target\n[Service]\nExecStartPre=/usr/bin/mkdir -p /run/adguardhome/statistics /run/adguardhome/querylog\nExecStartPre=/usr/local/sbin/piwifi-dns-sync --prepare\nExecStart=/opt/adguardhome/AdGuardHome -c /etc/adguardhome/AdGuardHome.yaml -w /opt/adguardhome/work --no-check-update\nRuntimeDirectory=adguardhome\nRuntimeDirectoryMode=0700\nRestart=on-failure\nRestartSec=3\nTimeoutStopSec=20\nUMask=0077\n[Install]\nWantedBy=multi-user.target\n'}
    raise ValueError('Unknown managed module')


def install_runtime(root,config):
    target=destination(root,'/etc/pi-control/runtime.json')
    if target.exists():
        if json.loads(target.read_text())!=config:raise ValueError('Runtime settings changed; explicit migration required')
    else:
        write(root,'/etc/pi-control/runtime.json',json.dumps(config,indent=2)+'\n')
        write(root,'/etc/systemd/journald.conf.d/pi-control.conf','[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\nRuntimeKeepFree=64M\n')
    control=destination(root,'/var/lib/pi-control/control');control.mkdir(parents=True,exist_ok=True,mode=0o755)
    for module in ('observer','camera','media'):
        path=destination(root,'/var/lib/pi-control/'+module);path.mkdir(parents=True,exist_ok=True,mode=0o700)
        if root==Path('/'):os.chown(path,config['desktop_uid'],-1)
    photos=destination(root,config['data_mount']+'/PiCamera');photos.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root==Path('/'):os.chown(photos,config['desktop_uid'],-1)


def links(root,link,target):
    parent=destination(root,str(PurePosixPath(link).parent));parent.mkdir(parents=True,exist_ok=True)
    path=parent/PurePosixPath(link).name
    if path.is_symlink():
        current=os.readlink(path)
        if current!=target and not current.startswith('/opt/pi-control/'):raise ValueError('Unmanaged symlink')
    elif path.exists():raise ValueError('Unmanaged destination exists')
    pending=path.with_name(path.name+'.link')
    if pending.exists() or pending.is_symlink():raise ValueError('Pending link requires review')
    pending.symlink_to(target);os.replace(pending,path)


def configure_module(base,root,module,config):
    uid=config['desktop_uid'];home=config['desktop_home']
    if module=='dashboard':
        auth=destination(root,'/etc/pi-control/dashboard/auth.env')
        if not auth.exists():write(root,'/etc/pi-control/dashboard/auth.env',f'PIWIFI_USER=admin\nPIWIFI_PASS={secrets.token_urlsafe(24)}\nPIWIFI_SECRET={secrets.token_hex(32)}\n',0o600)
        # Metadata only, never a copy of account/session credentials.
    if module=='network':
        for name in ('piwifi-helper','piwifi-guard','piwifi-dns-sync'):links(root,'/usr/local/sbin/'+name,'/opt/pi-control/network/current/helper/'+name)
        links(root,'/usr/local/lib/piwifi','/opt/pi-control/network/current')
        write(root,'/etc/sudoers.d/pi-control',f'{config["desktop_user"]} ALL=(root) NOPASSWD: /usr/local/sbin/piwifi-helper *\n',0o440)
        configure_fallback(root,config)
    if module=='media':
        extension='ddkjiahejlhfcafbddmgiahcphecmpfh'
        policy={'ExtensionSettings':{extension:{'installation_mode':'force_installed','update_url':'https://clients2.google.com/service/update2/crx'}},'3rdparty':{'extensions':{extension:{'defaultFiltering':'optimal','disableFirstRunPage':True}}}}
        write(root,'/etc/chromium/policies/managed/pi-control-ubol.json',json.dumps(policy))
        state='/var/lib/pi-control/media/nonstop.json'
        if not destination(root,state).exists():write(root,state,json.dumps({'enabled':False,'standby':True,'provider':'youtube'}),0o600,uid)
        pref=destination(root,home+'/.local/share/pi-control/chromium/Default/Preferences')
        if not pref.exists():write(root,home+'/.local/share/pi-control/chromium/Default/Preferences',json.dumps({'credentials_enable_service':False,'profile':{'password_manager_enabled':False}}),0o600,uid)
        if root==Path('/'):
            for part in (Path(home)/'.local',Path(home)/'.local/share',Path(home)/'.local/share/pi-control',Path(home)/'.local/share/pi-control/chromium',pref.parent):os.chown(part,uid,-1)
        write(root,home+'/.config/autostart/pi-control-session.desktop','[Desktop Entry]\nType=Application\nName=Pi Control desktop environment\nExec=systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP\n',0o644,uid)
        if root==Path('/'):
            for part in (Path(home)/'.config',Path(home)/'.config/autostart'):os.chown(part,uid,-1)
    if module=='dns':configure_dns(base,root,config)


def configure_fallback(root,config):
    path='/etc/NetworkManager/system-connections/pi-control-fallback.nmconnection'
    if destination(root,path).exists():return
    password=secrets.token_urlsafe(18)
    content=f'[connection]\nid=Pi-Fallback\nuuid={uuid.uuid4()}\ntype=wifi\ninterface-name=wlan0\nautoconnect=false\n[802-11-wireless]\nmode=ap\nssid=RaspPI4OfTT\nband=bg\n[802-11-wireless-security]\nkey-mgmt=wpa-psk\npsk={password}\n[ipv4]\nmethod=shared\naddress1=192.168.50.1/24\n[ipv6]\nmethod=disabled\n'
    write(root,path,content,0o600)
    write(root,'/etc/pi-control/network/fallback-access.json',json.dumps({'ssid':'RaspPI4OfTT','password':password}),0o600)
    if root==Path('/'):command(['nmcli','connection','load',path])  # Never activates or changes current Wi-Fi.


def configure_dns(base,root,config):
    from vendor_dns import configure
    configure(base,root,config,write,links)


def scope_of(module):return 'user' if module in ('audio','media','camera','render') else 'system'


def camera_idle(config):
    # No dependency on Dashboard being installed or reachable.
    script="""import socket,json
s=socket.socket(socket.AF_UNIX);s.settimeout(5)
s.connect('/run/user/"""+str(config['desktop_uid'])+"""/pi-camera.sock')
s.sendall(b'{"action":"status"}\\n');data=b''
while b'\\n' not in data and len(data)<262144:
 p=s.recv(4096)
 if not p:break
 data+=p
r=json.loads(data);assert r.get('ok'), 'Camera status unavailable'
d=r['data'];assert not d.get('recording') and not d.get('rendering'), 'Camera recording/rendering; finish session first'
"""
    user_command(config,['python3','-B','-c',script])


def activate(module,config):
    scope=scope_of(module)
    def run(args):return user_command(config,['systemctl','--user',*args]) if scope=='user' else command(['systemctl',*args])
    run(['daemon-reload'])
    for name in units(module,config):
        if '@' in name or name=='pi-control-media-browser.service':continue
        if module=='network' and name.endswith('.service'):continue
        run(['enable',name]);run(['restart',name]);run(['is-active','--quiet',name])


def save_units(root,module,config,release_path):
    scope=scope_of(module);folder='/etc/systemd/'+('user/' if scope=='user' else 'system/')
    rendered=units(module,config)
    write(root,'/'+str(release_path.relative_to(root))+'/installer-units.json',json.dumps(rendered,indent=2))
    for name,content in rendered.items():
        write(root,folder+name,content)
        for line in content.splitlines():
            if line.startswith('Alias='):
                for alias in line[6:].split():links(root,folder+alias,folder+name)


def restore_units(root,module,release):
    directory=f'/opt/pi-control/{module}/releases/{release}'
    rendered=json.loads(destination(root,directory+'/installer-units.json').read_text())
    folder='/etc/systemd/'+('user/' if scope_of(module)=='user' else 'system/')
    for name,content in rendered.items():
        if not re.fullmatch(r'[a-z0-9@.-]+\.(?:service|timer)',name):raise ValueError('Invalid saved unit')
        write(root,folder+name,content)


@contextmanager
def deployment_lock(root):
    import fcntl
    folder=destination(root,'/var/lib/pi-control/control');folder.mkdir(parents=True,exist_ok=True)
    fd=os.open(folder/'installer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def install(base,root,config,requested,apply=False,packages=True,locked=False):
    manifest,catalog=verify_bundle(base);validate_host(config)
    metadata_path=destination(root,'/var/lib/pi-control/control/modules.json')
    installed=json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    selected=resolve_modules(requested,catalog,installed)
    plan={'modules':selected,'keep_dependencies':sorted(set(installed)-set(selected)),
          'packages':sorted({p for m in selected for p in catalog['modules'][m]['packages']}),
          'external_setup':{m:s['kind'] for m,s in catalog['modules'].items() if m not in MANAGED},
          'host_mutation':apply and root==Path('/')}
    if not apply:return plan
    preflight(config,root)
    if not locked:
        with deployment_lock(root):return install(base,root,config,requested,True,packages,True)
    if root==Path('/'):
        missing=[]
        for package in plan['packages']:
            result=subprocess.run(['dpkg-query','-W','-f=${Status}',package],capture_output=True,text=True,timeout=10)
            if result.returncode or result.stdout.strip()!='install ok installed':missing.append(package)
        if packages and missing:
            command(['apt-get','update'],300)
            command(['apt-get','install','-y','--no-install-recommends',*missing],900)
        command(['loginctl','enable-linger',config['desktop_user']])
        # Required hardware/journal permissions, without granting general sudo.
        for group in ('adm','video','audio','bluetooth','netdev'):
            if subprocess.run(['getent','group',group],capture_output=True).returncode==0:command(['usermod','-aG',group,config['desktop_user']])
    install_runtime(root,config)
    sys.path.insert(0,str(base/'files/dashboard'))
    from deployment_history import Ledger
    ledger=Ledger(destination(root,'/var/lib/pi-control/control/deploy-history.json'),config['generation'])
    for module in selected:
        spec=manifest['modules'][module];old=installed.get(module)
        if old and old.get('source_hash')==spec['source_hash']:continue
        if root==Path('/') and module in ('camera','render') and 'camera' in installed:camera_idle(config)
        release=spec['release'];prefix=f'/opt/pi-control/{module}'
        release_path=destination(root,prefix+'/releases/'+release)
        if release_path.exists():raise ValueError('Release retained from an earlier attempt; use a new build or inspect it explicitly')
        source=base/'files'/module;release_path.mkdir(parents=True)
        for member in sorted(source.rglob('*')):
            if member.is_symlink():raise ValueError('Package symlink not allowed')
            if member.is_file():
                relative=member.relative_to(source);dest=release_path/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(member,dest);dest.chmod(0o755 if relative.parts[0]=='helper' or relative.name=='AdGuardHome' else 0o644)
        old_link=prefix+'/current'
        try:
            links(root,old_link,prefix+'/releases/'+release)
            save_units(root,module,config,release_path)
            configure_module(base,root,module,config)
            if root==Path('/'):
                activate(module,config)
            installed[module]={'release':release,'source_hash':spec['source_hash'],'contract':1,'generation':config['generation']}
            if old:installed[module]['previous']={k:v for k,v in old.items() if k!='previous'}
            write(root,'/var/lib/pi-control/control/modules.json',json.dumps(installed,indent=2))
            ledger.record(module,release,spec['source_hash'],'installed')
        except Exception:
            if old:
                links(root,old_link,prefix+'/releases/'+old['release'])
                restore_units(root,module,old['release'])
                if root==Path('/'):activate(module,config)
                installed[module]=old
                write(root,'/var/lib/pi-control/control/modules.json',json.dumps(installed,indent=2))
            ledger.record(module,release,spec['source_hash'],'failed')
            raise
    return plan|{'installed':selected,'generation':config['generation']}


def rollback(base,root,config,module,apply=False):
    verify_bundle(base);validate_host(config)
    if module not in MANAGED:raise ValueError('Unknown rollback module')
    metadata=destination(root,'/var/lib/pi-control/control/modules.json')
    installed=json.loads(metadata.read_text());current=installed.get(module,{})
    previous=current.get('previous')
    if not previous:raise ValueError('No previous release for this module')
    plan={'module':module,'from':current['release'],'to':previous['release'],'state_rollback':False}
    if not apply:return plan
    preflight(config,root)
    with deployment_lock(root):
        if root==Path('/') and module in ('camera','render'):camera_idle(config)
        links(root,f'/opt/pi-control/{module}/current',f'/opt/pi-control/{module}/releases/'+previous['release'])
        try:
            restore_units(root,module,previous['release'])
            if root==Path('/'):activate(module,config)
        except Exception:
            links(root,f'/opt/pi-control/{module}/current',f'/opt/pi-control/{module}/releases/'+current['release'])
            restore_units(root,module,current['release'])
            if root==Path('/'):activate(module,config)
            raise
        installed[module]=previous
        write(root,'/var/lib/pi-control/control/modules.json',json.dumps(installed,indent=2))
        sys.path.insert(0,str(base/'files/dashboard'));from deployment_history import Ledger
        Ledger(destination(root,'/var/lib/pi-control/control/deploy-history.json'),config['generation']).record(module,previous['release'],previous['source_hash'],'rolled-back')
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('verify','discover','plan','install','rollback','import-history'))
    parser.add_argument('--config',type=Path);parser.add_argument('--user');parser.add_argument('--modules',default='dashboard,media,camera,dns')
    parser.add_argument('--root',type=Path,default=Path('/'));parser.add_argument('--apply',action='store_true');parser.add_argument('--no-packages',action='store_true');parser.add_argument('--history',type=Path)
    args=parser.parse_args();verify_bundle()
    if args.action=='verify':print(json.dumps({'ok':True,'bundle':'verified'}));return
    if args.action=='discover':
        if not args.user:parser.error('--user required')
        print(json.dumps(discover(args.user),indent=2));return
    if not args.config:parser.error('--config required')
    if args.config.is_symlink() or args.config.stat().st_size>16384:raise ValueError('Unsafe host config')
    config=json.loads(args.config.read_text());validate_host(config)
    if args.action=='rollback':
        print(json.dumps(rollback(BASE,args.root,config,args.modules,args.apply),indent=2));return
    if args.action=='import-history':
        if not args.history or not args.apply:parser.error('import-history requires --history and --apply')
        preflight(config,args.root)
        sys.path.insert(0,str(BASE/'files/dashboard'));from deployment_history import Ledger
        print(json.dumps({'imported':Ledger(destination(args.root,'/var/lib/pi-control/control/deploy-history.json'),config['generation']).import_legacy(args.history)}));return
    print(json.dumps(install(BASE,args.root,config,args.modules.split(','),apply=args.action=='install' and args.apply,packages=not args.no_packages),indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:raise SystemExit(str(error))
