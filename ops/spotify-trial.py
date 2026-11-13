#!/usr/bin/env python3
"""Isolated, bounded Spotify/SpotiAds trial on this Pi; no profile credential copies.

Run as the desktop user over the verified SSH connection. The extension is
pinned, the test browser has its own profile/port/cgroup, and status exports
only playback fields and numeric hook counters. Never collect network headers,
cookies, storage, login forms or console payloads.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import socket
import stat
import subprocess
import tarfile
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path.home()/'.local/share/pi-control-trials/spotify-ads-20261029'
ARCHIVE = Path('/tmp/pi-spotify-ads-20261029.tar.gz')
ARCHIVE_SHA = 'fad41f0060b6767170c611b037562fee13acd996ac31d529b951b8cd548077cb'
UNIT = 'pi-control-spotify-trial.service'
WATCH = 'pi-control-spotify-trial-watch.service'
PORT = 18773
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

STATE = r"""(()=>{
 const visible=e=>!!e&&e.getClientRects().length>0;
 const button=document.querySelector('[data-testid="control-button-playpause"],[data-testid="play-pause-button"]');
 const info=navigator.mediaSession?.metadata,label=button?.getAttribute('aria-label')||'';
 const clock=id=>{const s=document.querySelector('[data-testid="'+id+'"]')?.textContent?.trim();return s&&/^\d{1,3}:\d{2}(?::\d{2})?$/.test(s)?s.split(':').reduce((n,v)=>n*60+Number(v),0):null};
 const count=typeof totalAdsRemoved==='number'&&Number.isFinite(totalAdsRemoved)?totalAdsRemoved:null;
 return {title:(info?.title||'').slice(0,200),artist:(info?.artist||'').slice(0,150),
 login_required:[...document.querySelectorAll('[data-testid="login-button"],a[href*="accounts.spotify.com/login"]')].some(visible),
 paused:/pause|tạm dừng/i.test(label)?false:/play|phát/i.test(label)?true:null,
 position:clock('playback-position'),duration:clock('playback-duration'),
 ad_present:[...document.querySelectorAll('[data-testid="ad-label"],[data-testid="audio-ad"],[data-testid="track-info-advertiser"]')].some(visible),
 extension_loaded:count!==null,removed_ads:count,fetch_hook_observed:typeof isFetchInterceptionWorking==='boolean'?isFetchInterceptionWorking:null,
 websocket_hook_observed:typeof isWebScoketInterceptionWorking==='boolean'?isWebScoketInterceptionWorking:null};})()"""


def run(*args):
    return subprocess.check_output(args, text=True, timeout=15, stderr=subprocess.DEVNULL).strip()


def private(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink() or path.stat().st_uid!=os.getuid():raise RuntimeError('Unexpected trial directory ownership')
    path.chmod(0o700)


def prepare():
    if ARCHIVE.is_symlink() or not ARCHIVE.is_file() or ARCHIVE.stat().st_size>8*1024*1024:raise RuntimeError('Invalid trial archive')
    raw=ARCHIVE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ARCHIVE_SHA:raise RuntimeError('Trial checksum mismatch')
    private(ROOT)
    extension=ROOT/'extension'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=archive.getmembers();names=set()
        for m in members:
            p=PurePosixPath(m.name)
            if not m.isfile() or p.is_absolute() or '..' in p.parts or m.name in names or m.size>2*1024*1024:raise RuntimeError('Unsafe extension member')
            names.add(m.name)
        if extension.exists():
            for m in members:
                p=extension/m.name
                if p.is_symlink() or not p.is_file() or p.read_bytes()!=archive.extractfile(m).read():raise RuntimeError('Existing trial extension changed; inspect before proceeding')
        else:
            private(extension);archive.extractall(extension,filter='data')
    manifest=json.loads((extension/'manifest.json').read_text())
    assert manifest['manifest_version']==3 and manifest['host_permissions']==['https://open.spotify.com/*']
    profile=ROOT/'profile';private(profile);private(profile/'Default')
    preferences=profile/'Default/Preferences'
    if not preferences.exists():
        with preferences.open('x') as stream:json.dump({'credentials_enable_service':False,'profile':{'password_manager_enabled':False}},stream)
        preferences.chmod(0o600)
    return {'prepared':True,'extension':manifest['name'],'version':manifest['version'],'profile_is_separate':True,'port':PORT}


def start():
    result=prepare()
    active=run('systemctl','--user','show',UNIT,'-p','ActiveState','--value')
    if active=='active':
        guard()
        return dict(result,already_running=True)
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',PORT))==0:raise RuntimeError('Trial debug port belongs to another process')
    runtime=Path('/run/user')/str(os.getuid())
    displays=[p.name for p in sorted(runtime.glob('wayland-*')) if stat.S_ISSOCK(p.stat().st_mode)]
    if not displays:raise RuntimeError('No Wayland desktop available for trial login')
    cache=runtime/'pi-spotify-trial-cache';private(cache)
    args=['systemd-run','--user','--unit='+UNIT,'--collect','--quiet',
          '--property=MemoryMax=900M','--property=MemoryHigh=700M','--property=CPUQuota=150%',
          '--property=StandardOutput=null','--property=StandardError=null',
          'env','XDG_RUNTIME_DIR='+str(runtime),'WAYLAND_DISPLAY='+displays[0],
          '/usr/lib/chromium/chromium','--ozone-platform=wayland','--password-store=basic',
          '--user-data-dir='+str(ROOT/'profile'),'--disk-cache-dir='+str(cache),'--disk-cache-size=33554432',
          '--remote-debugging-address=127.0.0.1','--remote-debugging-port='+str(PORT),
          '--disable-extensions-except='+str(ROOT/'extension'),'--load-extension='+str(ROOT/'extension'),
          '--no-first-run','--no-default-browser-check','--autoplay-policy=no-user-gesture-required',
          '--app=https://open.spotify.com/']
    run(*args)
    guard()
    return dict(result,started=True,needs_direct_login=True,cpu_max_cores=1.5,pss_guard_mib=750)


def resource():
    group=run('systemctl','--user','show',UNIT,'-p','ControlGroup','--value')
    if not group.startswith('/user.slice/'):raise RuntimeError('Unexpected trial cgroup')
    base=Path('/sys/fs/cgroup')/group.lstrip('/');pss=0;count=0
    for pid in (base/'cgroup.procs').read_text().split():
        try:
            rows=Path('/proc',pid,'smaps_rollup').read_text().splitlines()
            pss+=next(int(row.split()[1]) for row in rows if row.startswith('Pss:'));count+=1
        except FileNotFoundError:continue  # Child exited during the snapshot.
    available=next(int(row.split()[1]) for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemAvailable:'))
    return {'processes':count,'pss_mib':round(pss/1024,1),'available_mib':round(available/1024,1)}


def guard():
    if run('systemctl','--user','show',WATCH,'-p','ActiveState','--value')!='active':
        run('systemd-run','--user','--unit='+WATCH,'--collect','--quiet','--property=CPUQuota=5%',
            '--property=StandardOutput=null','--property=StandardError=null','/usr/bin/python3','-B',str(Path(__file__).resolve()),'watch')
    return {'watchdog_started':True,'pss_limit_mib':750,'minimum_available_mib':512,'maximum_hours':2}


def watch():
    until=time.monotonic()+7200
    while run('systemctl','--user','show',UNIT,'-p','ActiveState','--value')=='active':
        try:
            usage=resource()
            reason=('pss_limit' if usage['pss_mib']>750 else 'host_memory_low' if usage['available_mib']<512 else 'trial_ttl' if time.monotonic()>until else '')
        except (OSError,ValueError,RuntimeError,StopIteration):reason='resource_check_unavailable';usage={}
        if reason:
            run('systemctl','--user','stop',UNIT)
            record=dict(reason=reason,usage=usage,stopped_at=int(time.time()))
            (ROOT/'trial-stop.json').write_text(json.dumps(record));(ROOT/'trial-stop.json').chmod(0o600)
            return record
        time.sleep(5)
    return {'trial_exited':True}


def pages():
    with HTTP.open(f'http://127.0.0.1:{PORT}/json/list',timeout=3) as response:
        raw=response.read(262145)
    if len(raw)>262144:raise RuntimeError('Too many trial targets')
    return [p for p in json.loads(raw) if p.get('type')=='page']


def evaluate(page,expression):
    import websocket
    endpoint=page.get('webSocketDebuggerUrl','')
    if not endpoint.startswith(f'ws://127.0.0.1:{PORT}/'):raise RuntimeError('Invalid trial endpoint')
    connection=websocket.create_connection(endpoint,timeout=5,suppress_origin=True)
    try:
        connection.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':expression,'returnByValue':True}}))
        until=time.monotonic()+6
        while time.monotonic()<until:
            result=json.loads(connection.recv())
            if result.get('id')==1:
                if result.get('error') or result.get('result',{}).get('exceptionDetails'):raise RuntimeError('Trial page evaluation unavailable')
                return result.get('result',{}).get('result',{}).get('value')
        raise RuntimeError('Trial status timeout')
    except websocket.WebSocketException:raise RuntimeError('Trial page did not respond within its deadline') from None
    finally:connection.close()


def status():
    output={'service':run('systemctl','--user','show',UNIT,'-p','ActiveState','-p','MainPID','-p','MemoryCurrent','-p','CPUUsageNSec')}
    try:output['resources']=resource()
    except (OSError,ValueError,RuntimeError,StopIteration):pass
    try:
        rows=pages()
        spotify=next((p for p in rows if urlsplit(p.get('url','')).hostname=='open.spotify.com'),None)
        if spotify:
            output['player']=evaluate(spotify,STATE)
            output['page']=urlsplit(spotify['url']).path
        else:output['login_window']=any(urlsplit(p.get('url','')).hostname=='accounts.spotify.com' for p in rows)
    except (OSError,ValueError,RuntimeError):output['browser_ready']=False
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','start','status','stop','guard','watch'));action=parser.parse_args().action
    if os.getuid()!=1000 or not Path('/etc/pi-control/runtime.json').exists():raise RuntimeError('Run as the Pi desktop user on the modular system')
    if action=='prepare':result=prepare()
    elif action=='start':result=start()
    elif action=='guard':result=guard()
    elif action=='watch':result=watch()
    elif action=='stop':run('systemctl','--user','stop',UNIT);result={'stopped':True,'profile_preserved':True}
    else:result=status()
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
