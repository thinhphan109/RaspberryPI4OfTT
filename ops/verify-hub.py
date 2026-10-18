"""Authenticated live smoke + short read-I/O audit; never print credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
sys.path.insert(0,'/opt/piwifi-web')
import app
from flask.sessions import SecureCookieSessionInterface

config=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
app.app.secret_key=config['PIWIFI_SECRET']
serializer=SecureCookieSessionInterface().get_signing_serializer(app.app)
token=serializer.dumps({'logged_in':True,'csrf':'verify-hub'})
http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
base='http://127.0.0.1:18765'
def get(path,method='GET',session_token=None):
    req=urllib.request.Request(base+path,method=method,headers={'Cookie':'session='+(session_token or token),'X-CSRF-Token':'verify-hub'})
    with http.open(req,timeout=20) as r:
        raw=r.read()
        return (json.loads(raw) if path.startswith('/api/') else raw,r.headers)

data,_=get('/api/hub');assert data['data']['ip']=='192.168.0.106'
assert all(row['state']=='active' for row in data['data']['apps']),data
print('Application catalog: all three services active')
challenge,headers=get('/api/dns-check','POST')
cookie=headers['Set-Cookie'].split(';')[0].split('=',1)[1]
domain=challenge['data']['domain']
# Prove challenge starts inconclusive and becomes positive only after matching DNS.
before,_=get('/api/dns-check',session_token=cookie);assert not before['data']['seen']
subprocess.run(['dig','@127.0.0.1',domain,'+short'],capture_output=True,check=True,timeout=10)
for attempt in range(5):
    time.sleep(1)
    after,_=get('/api/dns-check',session_token=cookie)
    if after['data']['seen']:break
assert after['data']['seen'] and after['data']['filtering'],after
print('DNS challenge: unseen -> matched; blocking probe PASS')

def io():
    result={}
    for pid in Path('/sys/fs/cgroup/system.slice/piwifi-web.service/cgroup.procs').read_text().split():
        result[pid]=int(dict(row.split(': ',1) for row in Path('/proc/'+pid+'/io').read_text().splitlines())['write_bytes'])
    return result
before_io=io()
for i in range(4):
    get('/api/hub');time.sleep(5)
after_io=io()
assert before_io.keys()==after_io.keys()
delta=sum(after_io[p]-before_io[p] for p in before_io)
print(json.dumps({'dashboard_read_sample_seconds':20,'web_process_write_bytes_delta':delta}))
assert delta==0
settings=__import__('yaml').safe_load(Path('/etc/adguardhome/AdGuardHome.yaml').read_text())
assert not settings['dhcp']['enabled'] and not settings['querylog']['file_enabled']
assert settings['statistics']['dir_path'].startswith('/run/')
assert '192.168.50.1' not in settings['dns']['bind_hosts']
stamp=Path('/etc/adguardhome/AdGuardHome.yaml').stat().st_mtime_ns
subprocess.run(['/usr/local/sbin/piwifi-dns-sync'],check=True,timeout=15)
assert Path('/etc/adguardhome/AdGuardHome.yaml').stat().st_mtime_ns==stamp
print('AdGuard Home policy and event sync no-op: PASS')
