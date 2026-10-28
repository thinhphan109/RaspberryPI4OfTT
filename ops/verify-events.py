"""Authenticated, read-only journal HTTP check. Run on Pi with sudo."""
import http.cookiejar
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request


def main():
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines()
             if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=15) as response:html=response.read().decode()
    for ident in ('event-list','event-summary','event-source','event-level','event-search','event-refresh','event-more'):
        assert len(re.findall(r'id="'+ident+'"',html))==1,ident
    def data(path):
        with client.open(base+path,timeout=15) as response:reply=json.load(response)
        assert reply['ok'];return reply['data']
    payload=data('/api/events?summary=1')
    assert isinstance(payload['events'],list) and len(payload['events'])<=400
    assert payload['meta']['available'] and payload['meta']['last_read']>0,payload['meta']
    assert payload['meta']['retention_days']==30 and payload['meta']['maximum']==2000
    assert isinstance(data('/api/events'),list)
    rows=payload['events']
    assert all(isinstance(r.get('message'),str) and len(r.get('detail',''))<=800 for r in rows)
    with client.open(base+'/static/operations.js',timeout=15) as response:
        assert '/api/events?summary=1' in response.read().decode()
    anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with anonymous.open(base+'/api/events?summary=1',timeout=15) as response:
        assert '/login' in response.geturl()
    print(json.dumps(dict(ok=True,events=len(rows),kinds=sorted({r.get('kind','system') for r in rows}),
                         last_read=payload['meta']['last_read'],limited=payload['meta']['limited'],
                         pending=payload['meta']['pending'],error=payload['meta']['error'],
                         checks=['authenticated journal','legacy API compatible','bounded details',
                                 'retention metadata','unique controls','static asset','anonymous rejected']),ensure_ascii=False))


if __name__=='__main__':main()
