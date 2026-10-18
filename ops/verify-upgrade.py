"""Explicit on-Pi verification. Credentials stay in process memory; stdout is a report."""
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0,'/opt/piwifi-web')
import app
from flask.sessions import SecureCookieSessionInterface

config=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
app.app.secret_key=config['PIWIFI_SECRET']
token=SecureCookieSessionInterface().get_signing_serializer(app.app).dumps(dict(logged_in=True,csrf='upgrade-verification'))
def get(path):
    req=urllib.request.Request('http://127.0.0.1:18765'+path,headers={'Cookie':'session='+token})
    with urllib.request.urlopen(req,timeout=5) as r:
        data=r.read()
        return json.loads(data) if path.startswith('/api/') else data

def cpu():
    total=0
    for unit in ('piwifi-web','piwifi-observer'):
        values=dict(row.split() for row in Path('/sys/fs/cgroup/system.slice/'+unit+'.service/cpu.stat').read_text().splitlines())
        total+=int(values['usage_usec'])
    return total

def io():
    result={}
    for unit in ('piwifi-web','piwifi-observer'):
        for pid in Path('/sys/fs/cgroup/system.slice/'+unit+'.service/cgroup.procs').read_text().split():
            try:result[pid]=int(dict(row.split(': ') for row in Path('/proc/'+pid+'/io').read_text().splitlines())['write_bytes'])
            except OSError:pass
    return result

def sd_sectors():return int(Path('/sys/block/mmcblk0/stat').read_text().split()[6])
db=Path('/var/lib/piwifi-observer/history.db')
def db_hash():return hashlib.sha256(db.read_bytes()).hexdigest() if db.exists() else None

html=get('/').decode()
assert 'gpio-board' in html and 'traffic-rx' in html and 'ssh-logins' in html
gpio=get('/api/gpio/status')['data']
assert gpio['supported'] and len(gpio['pins'])==40 and not gpio['control_enabled']
assert get('/api/security')['data']['supported']
assert not get('/api/metrics')['data']['stale']
assert get('/api/metrics')['data']['history_storage']=='ram'
print('Authenticated HTML and all new read APIs verified; 40 GPIO pins, control disabled.',flush=True)
before=cpu();writes=io();hash_before=db_hash();sectors=sd_sectors();start=time.monotonic()
for step in range(120):
    # 10 min: one metrics client, five metrics clients, then GPIO view.
    clients=1 if step<40 else 5
    for client in range(clients):get('/api/metrics')
    if step>=80:get('/api/gpio/status')
    if step%12==0:
        elapsed=time.monotonic()-start
        print('Measurement %ds, phase=%s'%(round(elapsed),'metrics' if step<40 else 'multi-client' if step<80 else 'GPIO'),flush=True)
    time.sleep(5)
elapsed=time.monotonic()-start
core_percent=(cpu()-before)/1000000/elapsed*100
after=io();write_delta=sum(after.get(pid,value)-value for pid,value in writes.items())
result=dict(seconds=round(elapsed,1),cpu_one_core_percent=round(core_percent,3),cpu_whole_pi_percent=round(core_percent/os.cpu_count(),3),service_process_write_bytes=write_delta,legacy_db_unchanged=hash_before==db_hash(),whole_host_sd_write_bytes=(sd_sectors()-sectors)*512,ram_history_points=len(get('/api/history')['data']))
print(json.dumps(result),flush=True)
assert result['cpu_whole_pi_percent']<1,result
assert write_delta==0,result
assert result['legacy_db_unchanged'],result
