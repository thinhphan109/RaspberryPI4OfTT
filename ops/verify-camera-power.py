"""Explicit on-Pi power smoke test, with bounded RAM recording, no secrets out.

Refuses to start during an existing recording/viewer. Does not stop other users'
recordings. Uses real authenticated HTTP, private viewer leases, actual FFmpeg.
"""
import http.cookiejar
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def main():
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines()
             if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=15) as response:
        html=response.read().decode()
    token=re.search(r'id="ops-csrf" value="([^"]+)"',html).group(1)

    def api(payload=None):
        request=urllib.request.Request(base+'/api/camera',data=json.dumps(payload).encode() if payload else None,
                                       headers={'Content-Type':'application/json','X-CSRF-Token':token})
        with client.open(request,timeout=12) as response:
            result=json.load(response)
        assert result['ok'],result
        return result['data']

    initial=api()
    assert not initial['recording'] and not initial['rendering'],'Recording active: do not interrupt'
    assert initial.get('viewers',0)==0,'Viewer active: do not interrupt'
    assert initial['automatic'],'Automatic is disabled; do not override the user'
    viewer_a,viewer_b=uuid.uuid4().hex,uuid.uuid4().hex
    def watch(viewer,enabled):return api(dict(action='watch',viewer=viewer,watching=enabled))
    def report(check,**extra):print(json.dumps(dict(check=check,**extra)),flush=True)
    def wait_ready():
        for _ in range(30):
            current=api()
            if current['available']:return current
            time.sleep(.2)
        raise AssertionError('No camera frame')
    def wait_idle(label):
        time.sleep(7)
        current=api()
        if current['viewers']:
            report(label,skipped='Another viewer arrived; camera must stay on')
        else:
            assert not current['enabled'],current
            report(label,enabled=False)

    try:
        watch(viewer_a,True);wait_ready();watch(viewer_b,True)
        current=watch(viewer_a,False)
        assert current['viewers']>=1 and current['enabled']
        report('one of two viewers leaves',enabled=True)
        if current['viewers']==1:
            api(dict(action='power',enabled=False))
            time.sleep(1)
            current=watch(viewer_b,True)
            assert not current['enabled'],'Heartbeat undid manual off'
            api(dict(action='power',enabled=True));wait_ready()
            report('manual off held across heartbeat, manual on works')
        watch(viewer_b,False);wait_idle('last viewer leaves, real camera closes')

        watch(viewer_a,True);wait_ready()
        started=api(dict(action='start',mode='interval',interval=2,storage='ram'))
        ident=started['session']['id']
        watch(viewer_a,False)
        time.sleep(7)
        current=api()
        assert current['recording'] and current['session']['id']==ident and current['enabled']
        assert current['session']['frames']>=3
        try:
            api(dict(action='power',enabled=False))
            raise AssertionError('Manual power off interrupted recording')
        except urllib.error.HTTPError as exc:assert exc.code==400
        report('recording survives no viewers and rejects manual off',frames=current['session']['frames'])
        # Own short test session only; never stop an unrelated session.
        if api()['session']['id']==ident:
            api(dict(action='stop'))
        wait_idle('recording finished, camera rests')

        watch(viewer_a,True);wait_ready()
        # No release: models browser crash. Status polling must not renew lease.
        time.sleep(21)
        current=api()
        if current['viewers']:
            report('expired browser lease',skipped='Another viewer arrived')
        else:
            assert not current['enabled'],current
            report('expired browser lease, real camera closes',enabled=False)
        report('PASS',last_recording=api()['last_result'])
    finally:
        watch(viewer_a,False);watch(viewer_b,False)


if __name__=='__main__':main()
