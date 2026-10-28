#!/usr/bin/env python3
"""Exercise explicit Spotify/YouTube searches, links and native playback.

Restores the initial YouTube selection and pause state; never prints auth data.
Uses progress and PipeWire evidence, not a claim of physical speaker listening.
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
REPORT=[]
def log(value):
 REPORT.append(value);print(json.dumps(value,ensure_ascii=False),flush=True)
 Path('/tmp/pi-media-r7-verification.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2))
def api(payload):
 start=time.monotonic();code,raw=read('/api/media',payload);data=json.loads(raw)
 if code!=200 or not data.get('ok'):raise RuntimeError(str((payload['action'],code,data.get('error'))))
 if payload['action']!='status' and payload['action']!='catalog_status':log({'action':payload['action'],'http':code,'response_ms':round((time.monotonic()-start)*1000)})
 return data['data']
def streams():
 graph=json.loads(subprocess.check_output(['pw-dump'],text=True,timeout=3))
 return sum(n.get('info',{}).get('state')=='running' and n.get('info',{}).get('props',{}).get('media.class')=='Stream/Output/Audio' and n.get('info',{}).get('props',{}).get('application.process.binary') in ('chromium','chromium-browser') for n in graph)
def search(provider,text,kind):
 start=time.monotonic();d=api(dict(action='catalog_search',provider=provider,query=text,kind=kind))
 while d['running'] and time.monotonic()-start<55:
  time.sleep(1);d=api({'action':'catalog_status'})
 assert not d['running'] and d['rows'],d
 assert all('/track/' in r['url'] for r in d['rows']) if kind=='tracks' else True
 assert not any(r['title']=='Top Song Lyrics' for r in d['rows'])
 log({'search':provider,'kind':kind,'seconds':round(time.monotonic()-start,2),'count':len(d['rows']),'first_title':d['rows'][0]['title']})
 return d['rows']
def wait_play(provider,url,title=None):
 start=time.monotonic();first=None;s={}
 while time.monotonic()-start<55:
  s=api({'action':'status'})
  if s.get('content_unavailable'):raise RuntimeError(s.get('notice'))
  match=(s.get('url','').split('&')[0]==url.split('&')[0]) if provider=='youtube' else (s.get('url')==url and s.get('track_matches') is True if '/track/' in url else s.get('context_url')==url)
  playing=s.get('provider','youtube')==provider and s.get('connected') and match and s.get('has_video') and not s.get('paused') and not s.get('ad') and not s.get('launch_pending')
  if playing:
   if title and title.casefold() not in s.get('title','').casefold():playing=False
   if first is None:first=(time.monotonic(),s.get('position',0))
   if time.monotonic()-first[0]>=2 and s.get('position',0)>first[1] and streams():
    log({'play':provider,'seconds':round(time.monotonic()-start,2),'title':s.get('title'),'progress_advanced':True,'audio_stream':True,'receipt':(s.get('command') or {}).get('state')});return s
  else:first=None
  time.sleep(1)
 raise RuntimeError('Playback not verified: '+json.dumps({k:s.get(k) for k in ('provider','connected','title','url','context_url','paused','notice','track_matches','command')},ensure_ascii=False))
initial=api({'action':'status'});log({'initial_content_unavailable':initial.get('content_unavailable'),'initial_notice':initial.get('notice')})
try:
 tracks=search('spotify','Billie Jean','tracks')
 song=next((r for r in tracks if 'Michael Jackson' in r.get('subtitle','') and r['title']=='Billie Jean'),tracks[0]);spotify_url=song['url']
 playlists=search('spotify','nhạc không lời','playlists')
 videos=search('youtube','nhạc không lời','videos');blocked={r['id'] for r in initial.get('preferences',{}).get('disliked',[])}
 video=next(r for r in videos if re.search(r'v=([\w-]{11})',r['url']).group(1) not in blocked);yt_url=video['url']
 api(dict(action='catalog_play',provider='youtube',url=yt_url));wait_play('youtube',yt_url,video['title'])
 api(dict(action='catalog_play',provider='spotify',url=spotify_url));wait_play('spotify',spotify_url,song['title'])
 ident=re.search(r'v=([\w-]{11})',yt_url).group(1);short='https://youtu.be/'+ident+'?si=trial'
 api(dict(action='play',url=short));wait_play('youtube','https://www.youtube.com/watch?v='+ident,video['title'])
 localized=spotify_url.replace('/track/','/intl-vi/track/')+'?si=trial'
 api(dict(action='play',url=localized));wait_play('spotify',spotify_url,song['title'])
 api(dict(action='catalog_play',provider='spotify',url=playlists[0]['url']));wait_play('spotify',playlists[0]['url'])
 api(dict(action='power',enabled=False));assert api({'action':'status'})['standby']
 cached=search('spotify','Billie Jean','tracks');time.sleep(3)
 quiet=api({'action':'status'});assert not quiet.get('standby') and streams()==0
 log({'cold_search_quiet':True,'cached_rows':len(cached)})
 uri='spotify:track:'+spotify_url.rsplit('/',1)[1]
 api(dict(action='play',url=uri));wait_play('spotify',spotify_url,song['title'])
 log({'matrix':'passed'})
finally:
 current=api({'action':'status'})
 if not current.get('paused',True) and current.get('can_toggle',True):
  api({'action':'toggle'})
  for _ in range(10):
   if api({'action':'status'}).get('paused') is True:break
   time.sleep(.5)
 if initial.get('provider','youtube')=='youtube' and initial.get('url','').startswith('https://www.youtube.com/watch?'):
  api(dict(action='play',url=initial['url']));wait_play('youtube',initial['url'])
  if initial.get('paused',True):api({'action':'toggle'})
  log({'original_youtube_restored':True,'original_paused':initial.get('paused',True)})
 final=api({'action':'status'});log({'final_paused':final.get('paused'),'final_provider':final.get('provider'),'guard_paused':final.get('bluetooth_guard',{}).get('paused')})
