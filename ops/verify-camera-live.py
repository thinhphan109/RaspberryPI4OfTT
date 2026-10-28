"""On-Pi, explicit bounded camera smoke test. No credentials printed.

Run with sudo -n python3 -B; records a short RAM trial and checks camera on.
Automatic mode may return the camera to idle after this script exits.
Does not configure A1, calibration, external storage, or other project services.
"""
import argparse
import hashlib
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage',default='ram')
    parser.add_argument('--remember-storage',action='store_true')
    args=parser.parse_args()
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines()
             if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=15) as response:
        html=response.read().decode()
    token=re.search(r'id="ops-csrf" value="([^"]+)"',html).group(1)

    def request(path,payload=None,csrf=True):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-CSRF-Token']=token
        call=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload else None,headers=headers)
        with client.open(call,timeout=15) as response:
            return response.read(),response.headers

    def action(**payload):
        result=json.loads(request('/api/camera',payload)[0])
        assert result['ok'],result
        return result['data']

    def state():return json.loads(request('/api/camera')[0])['data']

    before=state()
    assert not before['recording'] and not before['rendering'],'User recording active; stop diagnostic'
    assert not before.get('viewers',0),'Viewer active; stop diagnostic'
    if args.remember_storage:
        remembered=action(action='storage',storage=args.storage)
        assert remembered['storage_default']==args.storage
    try:
        request('/api/camera',{'action':'power','enabled':True},csrf=False)
        raise AssertionError('Missing CSRF was accepted')
    except urllib.error.HTTPError as exc:assert exc.code==403
    action(action='power',enabled=True)
    for _ in range(30):
        if state()['available']:break
        time.sleep(.2)
    else:raise AssertionError('No live webcam frame')
    frame,headers=request('/api/camera/frame')
    assert frame[:2]==b'\xff\xd8' and frame[-2:]==b'\xff\xd9'
    assert headers.get('Cache-Control')=='no-store'
    for bad in ({'action':'start','mode':'position','storage':'ram'},
                {'action':'start','mode':'interval','storage':'/tmp/unsafe'}):
        # Do not invalidate a calibration the user has already set.
        if bad['mode']=='position' and before['calibrated']:continue
        try:
            action(**bad)
            raise AssertionError('Unsafe recording configuration accepted')
        except urllib.error.HTTPError as exc:assert exc.code==400
    # Omit the path when testing the remembered UUID selection.
    action(action='start',mode='interval',interval=2,
           **({} if args.remember_storage else dict(storage=args.storage)))
    time.sleep(6.5)
    recording=state()
    assert recording['session']['frames']>=3,recording
    live=request('/api/camera/frame')[0]
    assert live[:2]==b'\xff\xd8'
    action(action='stop')
    for _ in range(60):
        result=state()
        if not result['rendering']:break
        time.sleep(.5)
    assert result['last_result']['state']=='ready',result
    ident=result['last_result']['id']
    video=request('/api/camera/video/'+ident+'?storage='+urllib.parse.quote(args.storage,safe=''))[0]
    assert video[4:8]==b'ftyp'
    action(action='power',enabled=False)
    time.sleep(1)
    assert not state()['enabled']
    if before['enabled']:
        action(action='power',enabled=True)
    print(json.dumps(dict(ok=True,recording=result['last_result'],video_bytes=len(video),
                          video_sha256=hashlib.sha256(video).hexdigest(),jpeg_bytes=len(frame),
                          storage=args.storage,checks=['login','csrf','live JPEG','position requires calibration','no SD fallback',
                                  'simultaneous preview/recording','MP4 download','power off/on']),ensure_ascii=False))


if __name__=='__main__':main()
