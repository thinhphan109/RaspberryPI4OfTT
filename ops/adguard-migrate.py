"""Pi-hole -> pinned AdGuard Home migration. Run as root; secrets never printed."""
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request
import bcrypt
import yaml

ROOT=Path('/var/lib/adguard-migration')
BASE=Path('/opt/adguardhome')
CONFIG=Path('/etc/adguardhome/AdGuardHome.yaml')
STAGE=CONFIG.with_name('stage.yaml')
CREDENTIAL=Path('/home/thinh/.config/adguardhome/credentials.json')
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SHA='3f7893c18e8aaadc456d0452839190561c306ca95175a2254958be80a769c1ae'

def run(args, timeout=150):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()

def api(path,port=18854,method='GET',data=None):
    c=json.loads(CREDENTIAL.read_text())
    auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode()
    req=urllib.request.Request(f'http://127.0.0.1:{port}/control/'+path,method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization':'Basic '+auth,'Content-Type':'application/json'})
    with HTTP.open(req,timeout=30) as response:
        text=response.read();return json.loads(text) if text else {}

def wait(port):
    for _ in range(30):
        try:
            status=api('status',port);assert status['running'];return
        except Exception: time.sleep(1)
    raise RuntimeError('AdGuard health check failed')

def current_hosts():
    hosts=['127.0.0.1']
    data=json.loads(run(['ip','-j','-4','addr','show','dev','wlan0']))
    import ipaddress
    for row in data:
        for a in row.get('addr_info',[]):
            ip=ipaddress.ip_address(a['local'])
            if ip.is_private and not ip.is_link_local and str(ip)!='192.168.50.1':hosts.append(str(ip))
    return list(dict.fromkeys(hosts))

def prepare():
    assert not BASE.exists() and not CONFIG.parent.exists(), 'Existing AdGuard installation requires review'
    archive=Path('/tmp/AdGuardHome_linux_arm64.tar.gz')
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==SHA
    ROOT.mkdir(mode=0o700,exist_ok=True)
    paths=['etc/pihole','etc/.pihole','opt/pihole','var/www/html/admin','usr/bin/pihole-FTL','usr/local/bin/pihole',
        'etc/systemd/system/pihole-FTL.service','etc/systemd/system/pihole-FTL.service.d',
        'etc/cron.d/pihole','etc/logrotate.d/pihole','etc/tmpfiles.d/pihole-trial.conf',
        'etc/bash_completion.d/pihole','etc/bash_completion.d/pihole-FTL',
        'etc/NetworkManager/dispatcher.d/90-piwifi-pihole','usr/local/sbin/piwifi-pihole-sync',
        'home/thinh/.config/pihole-trial','var/log/pihole','var/lib/logrotate/pihole']
    existing=[p for p in paths if Path('/'+p).exists() or Path('/'+p).is_symlink()]
    with tarfile.open(ROOT/'pihole-before.tar.gz','w:gz',dereference=False) as tar:
        for p in existing:tar.add('/'+p,arcname=p)
    (ROOT/'inventory.json').write_text(json.dumps(existing,indent=2))
    (ROOT/'package-before.txt').write_text(run(['dpkg-query','-W']))
    (ROOT/'dashboard-before.txt').write_text(str(Path('/opt/piwifi-web').resolve()))
    restore=ROOT/'restore.sh'
    restore.write_text('''#!/bin/sh
set -eu
systemctl disable --now adguardhome.service 2>/dev/null || true
systemctl stop adguardhome-stage.service 2>/dev/null || true
tar -xzpf /var/lib/adguard-migration/pihole-before.tar.gz -C /
systemctl daemon-reload
systemctl enable --now pihole-FTL.service
echo DNS-restored-to-Pi-hole
''')
    restore.chmod(0o700)
    BASE.mkdir(mode=0o755)
    shutil.copy2('/tmp/adguard-migration/AdGuardHome/AdGuardHome',BASE/'AdGuardHome')
    (BASE/'AdGuardHome').chmod(0o755)
    (BASE/'work').mkdir()
    CONFIG.parent.mkdir(mode=0o700)
    account=pwd.getpwnam('thinh')
    CREDENTIAL.parent.mkdir(mode=0o700,parents=True)
    os.chown(CREDENTIAL.parent,account.pw_uid,account.pw_gid)
    cred={'username':'admin','password':secrets.token_urlsafe(24)}
    fd=os.open(CREDENTIAL,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(cred,stream)
    os.chown(CREDENTIAL,account.pw_uid,account.pw_gid)
    # Import active Pi-hole sources and exact/regex exceptions without changing groups.
    db=sqlite3.connect('file:/etc/pihole/gravity.db?mode=ro',uri=True)
    filters=[{'enabled':True,'url':url,'name':'Imported Pi-hole list','id':i+1}
        for i,(url,) in enumerate(db.execute('SELECT address FROM adlist WHERE enabled=1'))]
    rules=[]
    for kind,domain in db.execute('SELECT type,domain FROM domainlist WHERE enabled=1'):
        rules.append(('@@' if kind in (0,2) else '') + (f'||{domain}^' if kind in (0,1) else f'/{domain}/'))
    db.close()
    # Keep the imported list, add AdGuard's own default DNS filter.
    filters.append({'enabled':True,'url':'https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt','name':'AdGuard DNS filter','id':100})
    data={'schema_version':34,'http':{'address':'127.0.0.1:18854','session_ttl':'24h'},
      'users':[{'name':cred['username'],'password':bcrypt.hashpw(cred['password'].encode(),bcrypt.gensalt()).decode()}],
      'auth_attempts':5,'block_auth_min':15,'language':'en','theme':'auto',
      'dns':{'bind_hosts':['127.0.0.1'],'port':53535,'upstream_dns':['https://cloudflare-dns.com/dns-query'],
        'bootstrap_dns':['1.1.1.1','1.0.0.1'],'fallback_dns':['1.1.1.1','1.0.0.1'],
        'ratelimit':100,'use_private_ptr_resolvers':False,'resolve_clients':False,'cache_size':4194304},
      'filtering':{'protection_enabled':True,'filtering_enabled':True,'blocking_mode':'null_ip','filters_update_interval':24},
      'filters':filters,'whitelist_filters':[],'user_rules':rules,'dhcp':{'enabled':False},'tls':{'enabled':False},
      'querylog':{'enabled':True,'file_enabled':False,'size_memory':2000,'interval':'24h','dir_path':'/run/adguardhome/querylog'},
      'statistics':{'enabled':True,'interval':'24h','dir_path':'/run/adguardhome/statistics'},
      'clients':{'runtime_sources':{'whois':False,'arp':False,'rdns':False,'dhcp':False,'hosts':False},'persistent':[]},
      'log':{'enabled':True,'file':'','verbose':False}}
    STAGE.write_text(yaml.safe_dump(data,sort_keys=False));STAGE.chmod(0o600)
    run([str(BASE/'AdGuardHome'),'-c',str(STAGE),'-w',str(BASE/'work'),'--check-config'])
    unit=f'''[Unit]
Description=AdGuard Home DNS
After=network.target
[Service]
Type=simple
ExecStartPre=/usr/bin/mkdir -p /run/adguardhome/statistics /run/adguardhome/querylog
ExecStart={BASE}/AdGuardHome -c {STAGE} -w {BASE}/work --no-check-update
RuntimeDirectory=adguardhome
RuntimeDirectoryMode=0700
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
UMask=0077
[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/adguardhome-stage.service').write_text(unit)
    run(['systemctl','daemon-reload']);run(['systemctl','start','adguardhome-stage'])
    wait(18854)
    api('filtering/refresh',method='POST',data={'whitelist':False})
    result=run(['dig','@127.0.0.1','-p','53535','doubleclick.net','+short'])
    assert result=='0.0.0.0',result
    assert run(['dig','@127.0.0.1','-p','53535','example.com','+short'])
    print(json.dumps({'phase':'prepare','version':run([str(BASE/'AdGuardHome'),'--version']),'filters':len(filters),'rules_imported':len(rules),'health':'passed'}),flush=True)

def cutover():
    assert STAGE.exists() and not CONFIG.exists()
    old_release=Path((ROOT/'dashboard-before.txt').read_text())
    assert old_release.parent==Path('/opt/piwifi-releases') and old_release.is_dir()
    with tarfile.open(ROOT/'dashboard-before.tar.gz','w:gz',dereference=False) as tar:
        tar.add(old_release,arcname=str(old_release).lstrip('/'))
    (ROOT/'restore.sh').write_text(f'''#!/bin/sh
set -eu
systemctl disable --now adguardhome.service 2>/dev/null || true
systemctl stop adguardhome-stage.service 2>/dev/null || true
rm -f /etc/NetworkManager/dispatcher.d/90-piwifi-dns
tar -xzpf /var/lib/adguard-migration/pihole-before.tar.gz -C /
tar -xzpf /var/lib/adguard-migration/dashboard-before.tar.gz -C /
test -L /opt/piwifi-web
ln -sfn {old_release} /opt/piwifi-web
systemctl daemon-reload
systemctl enable --now pihole-FTL.service
systemctl restart piwifi-web
echo DNS-and-dashboard-restored-to-Pi-hole
''')
    run(['systemd-run','--unit=adguard-migration-recovery','--on-active=10m','/bin/sh',str(ROOT/'restore.sh')])
    try:
        run(['systemctl','stop','adguardhome-stage'])
        data=yaml.safe_load(STAGE.read_text());data['http']['address']='0.0.0.0:18853';data['dns']['port']=53;data['dns']['bind_hosts']=current_hosts()
        CONFIG.write_text(yaml.safe_dump(data,sort_keys=False));CONFIG.chmod(0o600)
        run([str(BASE/'AdGuardHome'),'-c',str(CONFIG),'-w',str(BASE/'work'),'--check-config'])
        run(['systemctl','stop','pihole-FTL'])
        old_hook=Path('/etc/NetworkManager/dispatcher.d/90-piwifi-pihole')
        if old_hook.exists():old_hook.unlink()
        unit=Path('/etc/systemd/system/adguardhome-stage.service').read_text().replace(str(STAGE),str(CONFIG))
        unit=unit.replace('Type=simple','Type=simple\nExecStartPre=/usr/local/sbin/piwifi-dns-sync --prepare')
        Path('/etc/systemd/system/adguardhome.service').write_text(unit)
        run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','adguardhome'])
        wait(18853)
        assert run(['dig','@127.0.0.1','doubleclick.net','+short'])=='0.0.0.0'
        assert run(['dig','@127.0.0.1','example.com','+short'])
        print('Cutover healthy; recovery timer remains armed until Windows and dashboard verified.',flush=True)
    except BaseException:
        run(['/bin/sh',str(ROOT/'restore.sh')]);raise

def remove():
    wait(18853)
    assert run(['dig','@127.0.0.1','doubleclick.net','+short'])=='0.0.0.0'
    assert 'AdGuard Home' in Path('/opt/piwifi-web/apps.json').read_text()
    assert run(['systemctl','is-active','adguardhome'])=='active'
    run(['systemctl','disable','pihole-FTL'])
    inventory=json.loads((ROOT/'inventory.json').read_text())
    # Explicit inventoried project paths only. Shared packages/directories retained.
    for relative in inventory:
        path=Path('/')/relative
        if not (path.exists() or path.is_symlink()):continue
        if path.is_symlink() or path.is_file():path.unlink()
        elif path.is_dir():
            assert path.resolve()==path, str(path)
            shutil.rmtree(path)
    extra=['/usr/local/sbin/piwifi-pihole-sync','/var/lib/logrotate/pihole','/run/pihole-trial']
    for value in extra:
        path=Path(value)
        if path.is_symlink() or path.is_file():path.unlink()
        elif path.is_dir():shutil.rmtree(path)
    # pihole-meta contains dependency metadata only; do not autoremove dependencies.
    run(['dpkg','--remove','pihole-meta'])
    for p in ['/etc/systemd/system/adguardhome-stage.service',str(STAGE)]:Path(p).unlink(missing_ok=True)
    run(['systemctl','daemon-reload']);run(['systemctl','reset-failed'])
    run(['systemctl','stop','adguard-migration-recovery.timer'])
    print('Pi-hole active files, service, cron and metapackage removed. Shared packages and recovery archives retained.',flush=True)

assert os.geteuid()==0
def stagecheck():
    unit=Path('/etc/systemd/system/adguardhome-stage.service')
    body=unit.read_text()
    if 'ExecStartPre=/usr/bin/mkdir' not in body:
        run(['systemctl','stop','adguardhome-stage'])
        unit.write_text(body.replace('Type=simple','Type=simple\nExecStartPre=/usr/bin/mkdir -p /run/adguardhome/statistics /run/adguardhome/querylog'))
        run(['systemctl','daemon-reload']);run(['systemctl','start','adguardhome-stage'])
    wait(18854)
    api('filtering/refresh',method='POST',data={'whitelist':False})
    assert run(['dig','@127.0.0.1','-p','53535','doubleclick.net','+short'])=='0.0.0.0'
    assert run(['dig','@127.0.0.1','-p','53535','example.com','+short'])
    print('Staged DNS, filter and API health: PASS',flush=True)

{'prepare':prepare,'stagecheck':stagecheck,'cutover':cutover,'remove':remove}[sys.argv[1]]()
