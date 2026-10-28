"""Authenticated, read-only production gallery check. Run on Pi with sudo."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import urllib.error
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
    token=re.search(r'id="ops-csrf" value="([^"]+)"',html).group(1)
    def request(path,payload=None):
        call=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload else None,
                                   headers={'Content-Type':'application/json','X-CSRF-Token':token})
        with client.open(call,timeout=15) as response:return response.read(),response.headers
    def data(path,payload=None):
        result=json.loads(request(path,payload)[0]);assert result['ok'],result
        return result['data']

    rows=data('/api/camera',dict(action='list'))
    rows.sort(key=lambda row:row['storage']=='ram')
    for row in rows:
        query='?storage='+urllib.parse.quote(row['storage'],safe='')
        photos=data('/api/camera/photos/'+row['id']+query)
        if photos['indices']:break
    else:raise AssertionError('No existing photos available for this check')
    preference=Path('/home/thinh/.local/state/pi-camera/storage.json')
    before=preference.stat().st_mtime_ns if preference.exists() else None
    photo_base='/api/camera/photo/'+row['id']+'/'
    for index in {photos['indices'][0],photos['indices'][-1]}:
        jpeg,headers=request(photo_base+str(index)+query)
        assert jpeg[:2]==b'\xff\xd8' and jpeg[-2:]==b'\xff\xd9' and len(jpeg)<=2*1024**2
        assert headers.get_content_type()=='image/jpeg'
        assert headers['Cache-Control']=='no-store' and headers['X-Content-Type-Options']=='nosniff'
        assert headers['Content-Disposition'].startswith('inline;')
        download,headers=request(photo_base+str(index)+query+'&download=1')
        assert hashlib.sha256(download).digest()==hashlib.sha256(jpeg).digest()
        assert headers['Content-Disposition'].startswith('attachment;')
    for invalid in (photo_base+'20000'+query,'/api/camera/photos/invalid'+query):
        try:request(invalid)
        except urllib.error.HTTPError as exc:assert exc.code==400
        else:raise AssertionError('Invalid session/index was accepted')
    anonymous=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with anonymous.open(base+'/api/camera/photos/'+row['id']+query,timeout=15) as response:
        assert '/login' in response.geturl()
    after=preference.stat().st_mtime_ns if preference.exists() else None
    assert before==after,'Photo requests modified storage preference'
    print(json.dumps(dict(ok=True,session=row['id'],storage=row['storage'],photos=photos['total'],
        checks=['authenticated listing','first/last JPEG','original download bytes','no-store/nosniff',
                'invalid index/session rejected','anonymous rejected','storage preference unchanged']),ensure_ascii=False))


if __name__=='__main__':main()
