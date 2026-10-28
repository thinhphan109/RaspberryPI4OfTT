"""Bounded HTTP viewer/idle test; no recording, file writes, or forced power-off."""
import http.cookiejar
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import uuid


def main():
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines()
             if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=15) as response:html=response.read().decode()
    token=re.search(r'id="ops-csrf" value="([^"]+)"',html).group(1)
    def api(payload=None):
        request=urllib.request.Request(base+'/api/camera',data=json.dumps(payload).encode() if payload else None,
            headers={'Content-Type':'application/json','X-CSRF-Token':token})
        with client.open(request,timeout=12) as response:result=json.load(response)
        assert result['ok'],result
        return result['data']
    initial=api()
    if initial['recording'] or initial['rendering'] or initial['viewers'] or not initial['automatic'] or initial['manual_paused']:
        print(json.dumps(dict(skipped='Camera in use or manual intent present; preserve user state')))
        return
    viewer=uuid.uuid4().hex
    def watch(enabled):return api(dict(action='watch',viewer=viewer,watching=enabled))
    try:
        watch(True)
        for _ in range(30):
            state=api()
            if state['available']:break
            time.sleep(.2)
        else:raise AssertionError('No webcam frame')
        for _ in range(4):
            time.sleep(3);state=watch(True)
            assert state['available'] and not state['error'],state
    finally:
        watch(False)
    time.sleep(7)
    state=api()
    if state['viewers'] or state['recording']:
        print(json.dumps(dict(skipped='Another viewer/recording arrived; leave camera running')))
        return
    assert not state['enabled'] and not state['error'],state
    print(json.dumps(dict(ok=True,checks=['authenticated viewer opens real camera',
        'frames remain available over 12s','last-viewer release closes FFmpeg','intentional idle leaves no timeout error'])))


if __name__=='__main__':main()
