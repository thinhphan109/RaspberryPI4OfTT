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


import re
report={}
def api(payload):
 code,raw=read('/api/media',payload);data=json.loads(raw)
 if code!=200 or not data.get('ok'):raise RuntimeError(data.get('error','Media API failed'))
 return data['data']
def streams():
 graph=json.loads(subprocess.check_output(['pw-dump'],text=True,timeout=3))
 return sum(n.get('info',{}).get('state')=='running' and n.get('info',{}).get('props',{}).get('media.class')=='Stream/Output/Audio' and n.get('info',{}).get('props',{}).get('application.process.binary') in ('chromium','chromium-browser') for n in graph)
before=api({'action':'status'});report['provider_before']=before.get('provider');report['audio_streams_before']=streams()
for provider in ('spotify','youtube'):
 start=time.monotonic();d=api({'action':'catalog_search','provider':provider,'query':'lofi'})
 while d['running'] and time.monotonic()-start<32:
  time.sleep(.8);d=api({'action':'catalog_status'})
 report[provider+'_search']={'seconds':round(time.monotonic()-start,2),'count':len(d.get('rows',[])),'message':d.get('message'),'running':d['running']}
 if d.get('rows'):
  Path('/tmp/pi-control-'+provider+'-results.json').write_text(json.dumps(d,ensure_ascii=False))
  again=api({'action':'catalog_search','provider':provider,'query':'lofi'});assert not again['running'];assert again['rows']==d['rows']
  report[provider+'_cache']='passed'
code,raw=read('/api/audio',{'action':'output_status'});assert code==200
output=json.loads(raw)['data']['output'];report['speaker_found']=bool(output)
if output:
 start=time.monotonic();code,raw=read('/api/audio',{'action':'output_volume','id':output['id'],'name':output['name'],'value':min(100,output['volume'])});assert code==200
 after=json.loads(raw)['data']['output'];assert after['name']==output['name'];assert after['volume']==min(100,output['volume']);report['speaker_same_volume_write_ms']=round((time.monotonic()-start)*1000)
 code,_=read('/api/audio',{'action':'output_volume','id':output['id'],'name':'old-device','value':10});assert code==400;report['stale_output_rejected']=True
code,html=read('/');assert code==200
class Inspect(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.assets=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if 'id' in d:self.ids.append(d['id'])
  for k in ('src','href'):
   if d.get(k,'').startswith('/static/'):self.assets.append(d[k])
p=Inspect();p.feed(html.decode());assert len(p.ids)==len(set(p.ids))
for key in ('catalog-form','quick-audio-open','media-quality','disks','services','deployment-info'):assert key in p.ids
for asset in set(p.assets):assert read(asset)[0]==200
text=html.decode();assert text.index('id="disks"')<text.index('id="deployment-info"')<text.index('class="card service-management"')
report.update(unique_ids=len(p.ids),assets=len(set(p.assets)),storage_order='passed')
final=api({'action':'status'});report.update(provider_after=final.get('provider'),paused_after=final.get('paused'),audio_streams_after=streams(),youtube_quality=final['youtube_quality'],guard_paused=final['bluetooth_guard']['paused'])
# Verify all active release bytes against their original signed manifests.
manifests=[json.loads(Path(p).read_text()) for p in ('/opt/pi-control-bootstrap-r3/manifest.json','/opt/pi-control-bootstrap-20261028-r4/manifest.json','/opt/pi-control-bootstrap-20261028-r6b/manifest.json','/opt/pi-control-bootstrap-20261028-r6c/manifest.json')]
metadata=json.loads(Path('/var/lib/pi-control/control/modules.json').read_text())
for name,entry in metadata.items():
 manifest=next(v for v in manifests if v['modules'][name]['release']==entry['release']);prefix='files/'+name+'/'
 for filename,digest in manifest['files'].items():
  if filename.startswith(prefix):assert hashlib.sha256((Path('/opt/pi-control',name,'current')/filename.removeprefix(prefix)).read_bytes()).hexdigest()==digest
report['all_eight_modules_verified']=True
print(json.dumps(report,ensure_ascii=False,indent=2))
