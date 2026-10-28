"""Read-only authenticated Spotify integration smoke check; no source switching."""
import http.cookiejar
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


def main():
    env=dict(line.split('=',1) for line in Path('/etc/piwifi-web.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:18765'
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    form=urllib.parse.urlencode({'username':env['PIWIFI_USER'],'password':env['PIWIFI_PASS']}).encode()
    with client.open(base+'/login',data=form,timeout=15) as response:html=response.read().decode()
    assert len(re.findall('data-media-source="(?:youtube|spotify)"',html))==2
    for ident in ('media-spotify-account','media-spotify-account-state','media-spotify-login','media-spotify-filter','media-url-label','media-search'):
        assert len(re.findall('id="'+ident+'"',html))==1,ident
    token=re.search(r'id="ops-csrf" value="([^"]+)"',html)[1]
    with client.open(base+'/api/media',timeout=15) as response:reply=json.load(response)
    assert reply['ok'],reply
    provider=reply['data'].get('provider','youtube')
    assert provider in ('youtube','spotify')
    request=urllib.request.Request(base+'/api/media',data=b'{"action":"source","provider":"invalid"}',headers={'Content-Type':'application/json','X-CSRF-Token':token})
    try:client.open(request,timeout=15);raise AssertionError('invalid source accepted')
    except urllib.error.HTTPError as error:assert error.code==400
    request=urllib.request.Request(base+'/api/media',data=b'{"action":"spotify_login"}',headers={'Content-Type':'application/json'})
    try:client.open(request,timeout=15);raise AssertionError('missing CSRF accepted')
    except urllib.error.HTTPError as error:assert error.code==403
    for asset in ('media.js','studio.css'):
        with client.open(base+'/static/'+asset,timeout=15) as response:assert response.status==200
    assert Path('/opt/piwifi-web/spotify_player.py').is_file()
    print(json.dumps({'ok':True,'provider_unchanged':provider,'checks':['source controls','account controls','media status','invalid source rejected','CSRF enforced','assets','module packaged'],'pending':['Spotify login','real Free playback','real ad filtering','visual/iPhone']},ensure_ascii=False))


if __name__=='__main__':main()
