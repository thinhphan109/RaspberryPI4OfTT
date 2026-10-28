#!/usr/bin/env python3
"""Bounded production checks; never print auth data or navigate to another song.

Adds/removes one unique test shortcut and briefly pauses/resumes an already
playing player. Does not disconnect hardware or override a Bluetooth hold.
"""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import secrets
import string
import subprocess
import time
import urllib.error
import urllib.request

from flask import Flask
from flask.sessions import SecureCookieSessionInterface

BASE='http://127.0.0.1:18765'
CSRF=secrets.token_hex(24)
pid=subprocess.check_output(['systemctl','show','pi-control-dashboard.service','-p','MainPID','--value'],text=True).strip()
env=dict(part.split(b'=',1) for part in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in part)
app=Flask(__name__);app.secret_key=env[b'PIWIFI_SECRET'].decode()
cookie=SecureCookieSessionInterface().get_signing_serializer(app).dumps(dict(logged_in=True,csrf=CSRF))
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read(path, payload=None, csrf=True):
    headers={'Cookie':'session='+cookie}
    if payload is not None:
        headers['Content-Type']='application/json'
        if csrf:headers['X-CSRF-Token']=CSRF
    request=urllib.request.Request(BASE+path, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with HTTP.open(request, timeout=15) as response:return response.status,response.read(2*1024*1024)
    except urllib.error.HTTPError as exc:return exc.code,exc.read(8192)


def media(payload=None):
    code,raw=read('/api/media',payload)
    data=json.loads(raw)
    if code!=200 or not data.get('ok'):raise RuntimeError('Media API check failed: '+str(code))
    return data['data']


def confirmed(action):
    result=media(action)
    ident=(result.get('command') or {}).get('id')
    for _ in range(12):
        receipt=result.get('command') or {}
        if receipt.get('id')!=ident:raise RuntimeError('Another command replaced the check')
        if receipt.get('state')=='confirmed':return result
        if receipt.get('state')=='unconfirmed':break
        time.sleep(0.4);result=media()
    raise RuntimeError('Player did not confirm the control result')


def main():
    before=media();report={'provider':before.get('provider','youtube'),'shortcut_roundtrip':'not-run'}
    assert all(key in before for key in ('shortcuts','command','bluetooth_guard'))
    assert read('/api/media',dict(action='shortcut_save'),csrf=False)[0]==403
    if len(before['shortcuts'])<24:
        ident=None
        try:
            token=''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(22))
            test_url='https://open.spotify.com/playlist/'+token
            result=confirmed(dict(action='shortcut_save',provider='spotify',url=test_url,label='Kiểm tra ghim · tạm'))
            item=next(row for row in result['shortcuts'] if row['url']==test_url);ident=item['id']
            assert any(row['id']==ident for row in media()['shortcuts'])
            confirmed(dict(action='shortcut_remove',id=ident));ident=None
            assert len(media()['shortcuts'])==len(before['shortcuts'])
            report['shortcut_roundtrip']='passed'
        finally:
            if ident:media(dict(action='shortcut_remove',id=ident))
    else:report['shortcut_roundtrip']='skipped-full-list'
    graph=json.loads(subprocess.check_output(['pw-dump'],text=True,timeout=3))
    streams=[node for node in graph if node.get('info',{}).get('props',{}).get('media.class')=='Stream/Output/Audio'
        and node.get('info',{}).get('props',{}).get('application.process.binary') in ('chromium','chromium-browser')
        and node.get('info',{}).get('state')=='running']
    report['active_chromium_audio_streams']=len(streams)
    initially_playing=before.get('has_video') and before.get('paused') is False and not before.get('ad') and before.get('can_toggle',True) and (before.get('playback_observed',True) or streams)
    report['pause_resume']='skipped-not-observable-playing-or-ad'
    if initially_playing:
        try:
            result=confirmed(dict(action='toggle'));assert result.get('paused') is True
            report['pause_resume']='paused-confirmed'
        finally:
            current=media()
            if current.get('paused') and not current.get('bluetooth_guard',{}).get('paused'):
                result=confirmed(dict(action='toggle'));assert result.get('paused') is False
                report['pause_resume']='passed'
    final=media()
    report.update(guard=final['bluetooth_guard'],final_paused=final.get('paused'),
        volume_known=final.get('can_volume'),position_known=final.get('position_known'),playback_observed=final.get('playback_observed'),
        shortcut_count=len(final['shortcuts']))
    code,html=read('/');assert code==200
    class Inspect(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.assets=[]
        def handle_starttag(self,tag,attrs):
            d=dict(attrs)
            if 'id' in d:self.ids.append(d['id'])
            for key in ('src','href'):
                if d.get(key,'').startswith('/static/'):self.assets.append(d[key])
    parser=Inspect();parser.feed(html.decode());assert len(parser.ids)==len(set(parser.ids))
    for ident in ('media-shortcuts','media-shortcut-form','media-bt-guard','media-result'):assert ident in parser.ids
    for asset in set(parser.assets):assert read(asset)[0]==200
    report.update(html_unique_ids=len(parser.ids),assets_checked=len(set(parser.assets)))
    # A local read-only visual preview: production HTML/assets and GET snapshots.
    preview=Path('/tmp/pi-control-media-r5b-preview');preview.mkdir(mode=0o700,exist_ok=True)
    (preview/'index.html').write_bytes(html)
    (preview/'api').mkdir(exist_ok=True)
    (preview/'api/media').write_text(json.dumps(dict(ok=True,data=final)))
    for name in ('metrics','operation'):
        code,data=read('/api/'+name);assert code==200;(preview/'api'/name).write_bytes(data)
    for asset in set(parser.assets):
        relative=asset.split('?',1)[0].lstrip('/');path=preview/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(read(asset)[1])
    manifests=[json.loads(Path(p).read_text()) for p in ('/opt/pi-control-bootstrap-r3/manifest.json','/opt/pi-control-bootstrap-20261028-r4/manifest.json','/opt/pi-control-bootstrap-20261028-r5e/manifest.json')]
    metadata=json.loads(Path('/var/lib/pi-control/control/modules.json').read_text());verified=[]
    for name,entry in metadata.items():
        manifest=next(value for value in manifests if value['modules'][name]['release']==entry['release'])
        prefix='files/'+name+'/'
        for file,digest in manifest['files'].items():
            if file.startswith(prefix):assert hashlib.sha256((Path('/opt/pi-control',name,'current')/file.removeprefix(prefix)).read_bytes()).hexdigest()==digest
        verified.append(name)
    report['verified_modules']=verified
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
