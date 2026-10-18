"""Run on Pi: bounded live volume-cap smoke test, always restores settings."""
import json
from pathlib import Path
import socket
import time
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

def call(payload):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(15);s.connect('/run/user/1000/pi-media.sock')
        s.sendall(json.dumps(payload).encode()+b'\n')
        r=json.loads(s.makefile('rb').readline())
    if not r['ok']:raise RuntimeError(r.get('error'))
    return r['data']

before=call(dict(action='status'))
assert before['connected'] and before['has_video'], 'Need an existing Media video'
old=before['volume_schedule'];old={k:old[k] for k in ('enabled','start','end','limit')}
original_volume=before['volume']
now=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
schedule=dict(enabled=True,start=(now-timedelta(minutes=2)).strftime('%H:%M'),end=(now+timedelta(minutes=10)).strftime('%H:%M'),limit=20)
try:
    capped=call(dict(action='volume_schedule',schedule=schedule))
    assert capped['volume_schedule']['active'] and capped['volume']<=20,capped
    clamped=call(dict(action='volume',value=100))
    assert clamped['volume']<=20,clamped
    config=Path.home()/'.local/state/pi-media/nonstop.json'
    stamp=config.stat().st_mtime_ns
    time.sleep(10)
    tick=call(dict(action='status'))
    assert tick['volume']<=20 and config.stat().st_mtime_ns==stamp
    disabled=call(dict(action='volume_schedule',schedule=dict(schedule,enabled=False)))
    assert disabled['volume']<=20,'Disabling raised volume'
    assert disabled['url']==before['url'],'Smoke test navigated away'
    assert disabled['nonstop']==before['nonstop'],'Smoke test changed Nonstop'
    print(json.dumps(dict(result='PASS',up_next=tick['up_next'],cap=tick['volume'],no_periodic_settings_write=True,nonstop=tick['nonstop']),ensure_ascii=False))
finally:
    call(dict(action='volume_schedule',schedule=old))
    restored=call(dict(action='volume',value=original_volume))
    print(json.dumps(dict(restored_volume=restored['volume'],restored_schedule=restored['volume_schedule']),ensure_ascii=False))
