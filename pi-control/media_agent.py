"""RAM queue + fixed YouTube controls. No public browser debugging endpoint."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import os
from pathlib import Path
import re
import socketserver
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import websocket
from media_policy import PlaybackPolicy
from media_extras import Shortcuts, CommandReceipt, BluetoothGuard, youtube_destination, destination, link_destination
from runtime_config import modular, location, unit, desktop_runtime
if not modular():import audio_control
import spotify_player as spotify
from media_catalog import Catalog, is_search
import youtube_quality
from native_player import NativePlayer

PORT=18769
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
LOCK=threading.RLock()
QUEUE=[]
CURRENT=None
ERROR=''
END_LATCH=False
VOLUME=35
VOLUME_SCRIPT=None
HOOK_VOLUME=None
WS=None
WS_TARGET=None
SEQUENCE=0
NONSTOP=False
MANUAL_PAUSE=False
LAST_URL=''
LAST_PROGRESS=None
PROGRESS_AT=0
RECOVERY_AT=0
RECOVERY_COUNT=0
NONSTOP_NOTE='Đã tắt'
CONFIG=location('media_state',Path.home()/'.local/state/pi-media')/'nonstop.json'
VOLUME_SCHEDULE=dict(enabled=False,start='22:00',end='07:00',limit=30)
POLICY=PlaybackPolicy()
POLICY_NOTE=''
POLICY_RETRY_AT=0
STANDBY=False
WAKE_URL=''
WAKE_UNTIL=0
PROVIDER='youtube'
SPOTIFY_URL=spotify.HOME
SPOTIFY_AD_FILTER=True
SPOTIFY_PENDING=0
SHORTCUTS=Shortcuts(CONFIG.with_name('shortcuts.json'))
RECEIPT=CommandReceipt()
BT_GUARD=BluetoothGuard()
NATIVE=NativePlayer()
SPOTIFY_AD_GUARD=spotify.AdStallGuard()
GUARD_SCRIPT=None
GUARD_TARGET=''
GUARD_FILE=desktop_runtime()/'pi-media-bluetooth-hold.json'
YOUTUBE_LIST=''
YOUTUBE_PENDING=None
CATALOG=Catalog(desktop_runtime()/'pi-media-search-target.json')
YOUTUBE_QUALITY='240'
QUALITY_AT=0

def validate_schedule(d):
    if not isinstance(d,dict) or type(d.get('enabled')) is not bool:
        raise ValueError('Lịch âm lượng cần giá trị bật/tắt')
    for key in ('start','end'):
        if not isinstance(d.get(key),str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',d[key]):
            raise ValueError('Giờ phải có dạng HH:MM')
    if d['start']==d['end']:raise ValueError('Giờ bắt đầu và kết thúc phải khác nhau')
    if type(d.get('limit')) is not int or not 0<=d['limit']<=100:
        raise ValueError('Giới hạn âm lượng phải từ 0 đến 100')
    return {k:d[k] for k in ('enabled','start','end','limit')}

def volume_policy(now=None):
    now=now or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    at=now.strftime('%H:%M');s=VOLUME_SCHEDULE
    inside=(s['start']<=at<s['end']) if s['start']<s['end'] else (at>=s['start'] or at<s['end'])
    return dict(s,active=s['enabled'] and inside,timezone='Asia/Ho_Chi_Minh')

def limited_volume(value):
    s=volume_policy()
    return min(value,s['limit'] if s['active'] else 100,POLICY.sleep_cap())

def volume_tick(s):
    global VOLUME
    cap=volume_policy()
    if (not cap['active'] and not POLICY.sleep) or not s.get('has_video'):return
    VOLUME=limited_volume(s.get('volume',VOLUME))
    if HOOK_VOLUME!=VOLUME:install_volume_hook(VOLUME)
    # Only lower volume; ending a window never raises it. No periodic disk write.
    evaluate(f'(()=>{{window.__piMediaVolume={VOLUME}/100;const v=document.querySelector("video,audio");if(v&&v.volume>{VOLUME}/100)v.volume={VOLUME}/100;return true}})()')

def save_nonstop():
    """Write only explicit user actions, never periodic playback samples."""
    CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=json.dumps(dict(enabled=NONSTOP,manual_pause=MANUAL_PAUSE,url=LAST_URL,volume=VOLUME,volume_schedule=VOLUME_SCHEDULE,preferences=POLICY.dump(),standby=STANDBY,provider=PROVIDER,spotify_url=SPOTIFY_URL,spotify_ad_filter=SPOTIFY_AD_FILTER,bluetooth_guard=BT_GUARD.enabled,youtube_quality=YOUTUBE_QUALITY))
    tmp=CONFIG.with_suffix('.tmp');tmp.write_text(data);tmp.chmod(0o600);tmp.replace(CONFIG)

def load_nonstop():
    global NONSTOP,MANUAL_PAUSE,LAST_URL,VOLUME,VOLUME_SCHEDULE,STANDBY,PROVIDER,SPOTIFY_URL,SPOTIFY_AD_FILTER,YOUTUBE_QUALITY
    try:
        d=json.loads(CONFIG.read_text())
        if not isinstance(d,dict):return
        NONSTOP=d.get('enabled') is True;MANUAL_PAUSE=d.get('manual_pause') is True
        STANDBY=d.get('standby') is True
        if d.get('youtube_quality') in youtube_quality.CHOICES:YOUTUBE_QUALITY=d['youtube_quality']
        BT_GUARD.enabled=d.get('bluetooth_guard',True) is True
        POLICY.load(d.get('preferences'))
        PROVIDER=d.get('provider') if d.get('provider') in ('youtube','spotify') else 'youtube'
        SPOTIFY_AD_FILTER=d.get('spotify_ad_filter',True) is True
        try:SPOTIFY_URL=spotify.url(d.get('spotify_url',spotify.HOME))
        except ValueError:SPOTIFY_URL=spotify.HOME
        if type(d.get('volume')) in (int,float) and 0<=d['volume']<=100:VOLUME=d['volume']
        if 'volume_schedule' in d:VOLUME_SCHEDULE=validate_schedule(d['volume_schedule'])
        LAST_URL=youtube_url(d.get('url'))
    except (OSError,ValueError,TypeError):LAST_URL=''

def youtube_url(value):
    if not isinstance(value,str) or len(value)>2048:raise ValueError('Link YouTube không hợp lệ')
    p=urllib.parse.urlsplit(value)
    if p.scheme!='https' or p.username or p.password or p.port:raise ValueError('Chỉ nhận link HTTPS YouTube')
    if p.hostname=='youtu.be':ident=p.path.strip('/')
    elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'):
        if p.path=='/watch':ident=urllib.parse.parse_qs(p.query).get('v',[''])[0]
        elif p.path.startswith(('/shorts/','/live/')):ident=p.path.split('/')[2]
        else:raise ValueError('Gửi link của một video, không phải trang tìm kiếm/playlist')
    else:raise ValueError('Chỉ nhận link YouTube')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident):raise ValueError('Mã video YouTube không hợp lệ')
    return 'https://www.youtube.com/watch?v='+ident

def pages():
    with HTTP.open(f'http://127.0.0.1:{PORT}/json/list',timeout=2) as r:
        return [p for p in json.load(r) if p.get('type')=='page']

def target():
    with CATALOG.lock:excluded=set(CATALOG.owned)
    rows=[p for p in pages() if p['id'] not in excluded and not is_search(p.get('url'))]
    if PROVIDER=='spotify':
        for p in rows:
            if spotify.is_page(p.get('url'),auth=True):return p
    for p in rows:
        if p['url'].startswith(('https://www.youtube.com/','https://music.youtube.com/')):return p
    for p in rows:
        if spotify.is_page(p.get('url'),auth=True):return p
    for p in rows:
        # Chromium --app=about:blank can expose chrome://newtab/ on cold start.
        # Only the dedicated profile's exact empty startup pages are eligible.
        if p['url'] in ('about:blank','chrome://newtab/'):return p
    raise ValueError('Cửa sổ Media chưa ở YouTube/Spotify; kiểm tra desktop Pi')

def cdp(method,params=None):
    global WS,WS_TARGET,SEQUENCE
    p=target();url=p['webSocketDebuggerUrl']
    if not url.startswith(f'ws://127.0.0.1:{PORT}/'):raise ValueError('Invalid browser endpoint')
    if WS is None or WS_TARGET!=p['id']:
        if WS is not None:WS.close()
        WS=websocket.create_connection(url,timeout=3,suppress_origin=True);WS_TARGET=p['id']
    SEQUENCE+=1;ident=SEQUENCE
    try:
        WS.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
        while True:
            r=json.loads(WS.recv())
            if r.get('id')==ident:
                if 'error' in r:raise ValueError('Trình duyệt từ chối thao tác')
                return r.get('result',{})
    except websocket.WebSocketTimeoutException:
        WS.close();WS=None
        raise ValueError('Chromium đang chờ trang/hộp thoại; kiểm tra desktop Pi (keyring hoặc đăng nhập).')
    except Exception:
        WS.close();WS=None
        raise

def evaluate(expression):
    r=cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
    if r.get('exceptionDetails'):raise ValueError('Trang chưa sẵn sàng hoặc bị chặn tự phát')
    return r.get('result',{}).get('value')

def open_browser():
    if STANDBY:raise ValueError('Media đang nghỉ; bấm Bật Media trước')
    subprocess.run(['systemctl','--user','start',unit('pi-media-browser')],check=True,timeout=8,capture_output=True)

def set_power(enabled):
    """Only the dedicated browser; networking, DNS and desktop stay available."""
    global STANDBY,LAST_URL,VOLUME,WS,WS_TARGET,VOLUME_SCRIPT,HOOK_VOLUME,RECOVERY_AT,RECOVERY_COUNT,WAKE_URL,WAKE_UNTIL,SPOTIFY_URL
    if type(enabled) is not bool:raise ValueError('Trạng thái Media cần giá trị bật/tắt')
    if enabled:
        previous=STANDBY;STANDBY=False
        try:cold=not bool(pages())
        except Exception:cold=True
        try:save_nonstop();open_browser()
        except Exception:
            STANDBY=previous;save_nonstop();raise
        RECOVERY_AT=0;RECOVERY_COUNT=0
        if (previous or cold) and PROVIDER=='spotify':
            WAKE_URL=spotify.HOME if MANUAL_PAUSE or POLICY.sleep_state()['expired'] else SPOTIFY_URL
            WAKE_UNTIL=time.monotonic()+30
        elif previous or cold:
            WAKE_URL='https://www.youtube.com/'
            if NONSTOP and LAST_URL and not MANUAL_PAUSE and not POLICY.sleep_state()['expired'] and not POLICY.reason(LAST_URL.split('v=')[1],automatic=False):WAKE_URL=LAST_URL
            WAKE_UNTIL=time.monotonic()+30
    else:
        if not STANDBY:
            current=status()
            if current.get('url'):
                if PROVIDER=='spotify':SPOTIFY_URL=current.get('context_url') or current['url']
                else:LAST_URL=current['url']
            level=current.get('volume')
            if current.get('has_video') and current.get('can_volume') is not False and type(level) in (int,float) and math.isfinite(level) and 0<=level<=100:VOLUME=level
        subprocess.run(['systemctl','--user','stop',unit('pi-media-browser')],check=True,timeout=8,capture_output=True)
        previous=STANDBY;STANDBY=True
        try:save_nonstop()
        except Exception:STANDBY=previous;raise
        if WS:
            try:WS.close()
            except Exception:pass
        WS=None;WS_TARGET=None;VOLUME_SCRIPT=None;HOOK_VOLUME=None
        WAKE_URL=''
    return status()

def resume_tick():
    """Navigate explicitly after cold start; homepage previews are not playback."""
    global WAKE_URL,SPOTIFY_PENDING
    if not WAKE_URL:return
    if STANDBY or time.monotonic()>WAKE_UNTIL:
        WAKE_URL='';return
    if PROVIDER=='spotify':
        if WAKE_URL==spotify.HOME:
            install_volume_hook(limited_volume(VOLUME));cdp('Page.navigate',{'url':spotify.HOME})
        else:spotify_dispatch(dict(action='play',url=WAKE_URL))
    elif WAKE_URL=='https://www.youtube.com/':cdp('Page.navigate',{'url':WAKE_URL})
    elif MANUAL_PAUSE or POLICY.sleep_state()['expired']:WAKE_URL='';return
    else:dispatch(dict(action='play',url=WAKE_URL))
    WAKE_URL=''

def install_volume_hook(level):
    global VOLUME_SCRIPT,HOOK_VOLUME
    if VOLUME_SCRIPT:
        try:cdp('Page.removeScriptToEvaluateOnNewDocument',{'identifier':VOLUME_SCRIPT})
        except Exception:pass
    # YouTube may reset video volume on navigation. Apply before autoplay starts.
    script=f"""window.__piMediaVolume={level}/100;
const applyPiVolume=e=>{{const v=e.target;if(v instanceof HTMLMediaElement && Math.abs(v.volume-window.__piMediaVolume)>0.001)v.volume=window.__piMediaVolume}};
for(const event of ['loadedmetadata','play','volumechange'])document.addEventListener(event,applyPiVolume,true);"""
    VOLUME_SCRIPT=cdp('Page.addScriptToEvaluateOnNewDocument',{'source':script})['identifier']
    HOOK_VOLUME=level

def play(url):
    global CURRENT,END_LATCH,POLICY_RETRY_AT
    if POLICY.sleep_state()['expired']:raise ValueError('Đã hết hẹn giờ ngủ; bấm Phát để nghe tiếp')
    install_volume_hook(limited_volume(VOLUME))
    cdp('Page.navigate',{'url':url+('&list='+YOUTUBE_LIST if YOUTUBE_LIST else '')});CURRENT=url;END_LATCH=False
    POLICY.observe(url.split('v=')[1]);POLICY_RETRY_AT=time.monotonic()+8

STATE_JS="""(()=>{const v=document.querySelector('video');const n=x=>Number.isFinite(x)?x:0;
const next=document.querySelector('.ytp-next-button');const href=next?.href||'';
const id=new URL(href||location.href,location.href).searchParams.get('v');
const a=[...document.querySelectorAll('ytd-compact-video-renderer a#video-title,yt-lockup-view-model a.ytLockupMetadataViewModelTitle')].find(a=>new URL(a.href,location.href).searchParams.get('v')===id);
return {title:(document.querySelector('h1.ytd-watch-metadata')?.textContent||document.title).trim().slice(0,300),
up_next:{url:href,title:(a?.getAttribute('title')||a?.textContent||next?.getAttribute('data-tooltip-text')||'Bài YouTube đề xuất').trim().slice(0,300)},
recommendations:[...document.querySelectorAll('ytd-compact-video-renderer a#video-title,yt-lockup-view-model a.ytLockupMetadataViewModelTitle')].slice(0,40).map(a=>({url:a.href,title:(a.getAttribute('title')||a.textContent||'Video đề xuất').trim().slice(0,300)})),
url:location.href,has_video:!!v,paused:v?v.paused:true,ended:v?v.ended:false,
position:v?n(v.currentTime):0,duration:v?n(v.duration):0,volume:v?Math.round(v.volume*100):0,video_height:v?v.videoHeight:0,
muted:v?v.muted:false,ad:!!document.querySelector('.ad-showing'),
autoplay:document.querySelector('.ytp-autonav-toggle-button')?.getAttribute('aria-checked')==='true',
notice:v?.error?'Video báo lỗi; kiểm tra trên desktop.':''};})()"""

def next_video(current,rows):
    choices=[dict(url=u,title='Video '+u.split('v=')[1],source='Hàng đợi của bạn',queue_index=i) for i,u in enumerate(QUEUE)]
    choices.extend(dict(r,source='YouTube đề xuất') for r in rows if isinstance(r,dict))
    seen=set()
    for row in choices:
        try:url=youtube_url(row.get('url'))
        except ValueError:continue
        if url in seen or url==current:continue
        seen.add(url)
        if POLICY.reason(url.split('v=')[1]):continue
        return dict(url=url,title=str(row.get('title') or 'Bài YouTube đề xuất')[:300],source=row['source'],**({'queue_index':row['queue_index']} if 'queue_index' in row else {}))
    return None

def move_next(s):
    global LAST_URL,MANUAL_PAUSE,POLICY_NOTE
    choice=s.get('up_next')
    if not choice:raise ValueError('Chưa có bài phù hợp; chọn video khác hoặc điều chỉnh chống lặp')
    play(youtube_url(choice['url']))
    if 'queue_index' in choice:QUEUE.pop(choice['queue_index'])
    LAST_URL=choice['url'];MANUAL_PAUSE=False;POLICY_NOTE=''

PAUSE_JS="""(()=>{const v=document.querySelector('video');if(v)v.pause();const b=document.querySelector('.ytp-autonav-toggle-button');if(b&&b.getAttribute('aria-checked')==='true')b.click();return true})()"""

def sleep_tick(s):
    global NONSTOP_NOTE
    if not POLICY.sleep_state()['expired']:return False
    NONSTOP_NOTE='Hết hẹn giờ ngủ; bấm Phát để nghe tiếp'
    if s.get('connected'):evaluate(spotify.PAUSE_JS if PROVIDER=='spotify' else PAUSE_JS)
    return True

def preference_tick(s,now=None):
    global POLICY_RETRY_AT,POLICY_NOTE,MANUAL_PAUSE
    now=time.monotonic() if now is None else now
    if not s.get('url') or s.get('ad') or now<POLICY_RETRY_AT:return False
    ident=s['url'].split('v=')[1]
    # Revisit checks apply to automatic navigation; explicit Play marks tracked.
    reason=POLICY.reason(ident,automatic=ident!=POLICY.tracked)
    if reason:
        POLICY_NOTE=reason+' · đang chọn bài khác'
        POLICY_RETRY_AT=now+8
        if s.get('up_next'):move_next(s)
        else:
            evaluate(PAUSE_JS);MANUAL_PAUSE=True
            POLICY_NOTE='Chưa có bài phù hợp; chọn bài khác hoặc điều chỉnh chống lặp'
        return True
    if s.get('has_video'):POLICY.observe(ident,now)
    return False

def player_status():
    if PROVIDER=='spotify':return spotify_status()
    if STANDBY:
        return dict(standby=True,connected=False,title='Media đang nghỉ',queue=list(QUEUE),error='',nonstop=NONSTOP,manual_pause=MANUAL_PAUSE,nonstop_note='Đã đóng trình duyệt; Nonstop chờ bạn bật Media',volume_schedule=volume_policy(),up_next=None,preferences=POLICY.summary(),policy_note='Dashboard, Wi-Fi và DNS vẫn hoạt động.')
    try:
        d=evaluate(STATE_JS);d['connected']=True
        if not d.get('title') and not d.get('has_video'):
            d['notice']='Trang chưa tải. Kiểm tra hộp thoại keyring trên desktop Pi rồi thử lại.'
        # Export only the dedicated player's YouTube video, never arbitrary URLs.
        try:d['context_url']=youtube_destination(d['url'])
        except ValueError:d['context_url']=''
        try:d['url']=youtube_url(d['url'])
        except ValueError:d['url']=''
        rows=[d.pop('up_next',None)]+d.pop('recommendations',[])
        d['up_next']=next_video(d['url'],rows);d['volume_schedule']=volume_policy()
        d['queue']=list(QUEUE);d['queue_note']='Hàng đợi trong RAM; mất khi agent khởi động lại.'
        d['error']=ERROR;d['standby']=False
        d['launch_pending']=YOUTUBE_PENDING is not None
        if YOUTUBE_LIST:d['collection_url']='https://www.youtube.com/playlist?list='+YOUTUBE_LIST
        d.update(nonstop=NONSTOP,manual_pause=MANUAL_PAUSE,nonstop_note=NONSTOP_NOTE)
        d.update(preferences=POLICY.summary(),policy_note=POLICY_NOTE)
        return d
    except Exception:
        return dict(connected=False,title='Chưa kết nối cửa sổ Media',queue=list(QUEUE),error=ERROR,nonstop=NONSTOP,manual_pause=MANUAL_PAUSE,nonstop_note=NONSTOP_NOTE,volume_schedule=volume_policy(),up_next=None,preferences=POLICY.summary(),policy_note=POLICY_NOTE)


def spotify_status():
    common=dict(provider='spotify',standby=STANDBY,connected=False,title='Spotify',queue=[],up_next=None,
                error=ERROR,nonstop=False,manual_pause=MANUAL_PAUSE,nonstop_note='',preferences=POLICY.summary(),
                volume_schedule=volume_policy(),spotify_ad_filter=SPOTIFY_AD_FILTER,
                policy_note='Spotify tự quản lý đề xuất và hàng đợi. Chống lặp/Không thích của Dashboard dùng cho YouTube.')
    if STANDBY:return dict(common,title='Media đang nghỉ')
    try:
        page=target()
        if not spotify.is_page(page.get('url')):
            if not spotify.is_page(page.get('url'),auth=True):
                return dict(common,notice='Chọn bài trong kết quả tìm kiếm hoặc dán link để bắt đầu.')
            return dict(common,connected=True,login_required=True,notice='Hoàn tất đăng nhập Spotify trực tiếp trên Pi; Dashboard không nhận mật khẩu.')
        result=dict(common,**spotify.state(evaluate(spotify.state_script(SPOTIFY_URL))),connected=True,launch_pending=bool(SPOTIFY_PENDING))
        try:result['context_url']=spotify.public_destination(page.get('url'))
        except ValueError:result['context_url']=''
        return result
    except Exception:return dict(common,notice='Chưa đọc được Spotify; bấm mở Spotify hoặc kiểm tra cửa sổ trên Pi.')


def status():
    if WAKE_URL:
        data=dict(provider=PROVIDER,standby=STANDBY,connected=False,launch_pending=True,title='Đang mở nội dung…',
                  queue=list(QUEUE) if PROVIDER=='youtube' else [],nonstop=NONSTOP if PROVIDER=='youtube' else False,
                  preferences=POLICY.summary(),volume_schedule=volume_policy(),spotify_ad_filter=SPOTIFY_AD_FILTER,error='')
    else:data=player_status()
    try:data['shortcuts']=SHORTCUTS.rows()
    except (OSError,ValueError,TypeError,AttributeError):
        data['shortcuts']=[];data['shortcut_error']='Không đọc được danh sách ghim; dữ liệu hiện có được giữ nguyên.'
    data['bluetooth_guard']=BT_GUARD.summary()
    data['command']=RECEIPT.observe(data)
    data['youtube_quality']=YOUTUBE_QUALITY
    data['provider']=PROVIDER
    data['youtube_nonstop']=NONSTOP
    data['spotify_ad_recovery']=SPOTIFY_AD_GUARD.summary()
    return data


def select_source(source):
    global PROVIDER,SPOTIFY_PENDING,ERROR,WS,WS_TARGET,VOLUME_SCRIPT,HOOK_VOLUME,WAKE_URL
    if source not in ('youtube','spotify'):raise ValueError('Nguồn phát không hợp lệ')
    if STANDBY:raise ValueError('Bật Media trước khi chọn nguồn phát')
    open_browser()
    # Source switching is explicit. Pause only this dedicated Media window.
    try:
        if PROVIDER=='spotify' and spotify.is_page(target().get('url')):
            evaluate(spotify.PAUSE_JS);spotify.ad_filter(evaluate,False,False)
        elif PROVIDER=='youtube':evaluate('(()=>{const v=document.querySelector("video");if(v)v.pause();return true})()')
    except Exception:pass
    previous=PROVIDER
    try:
        destination=SPOTIFY_URL if source=='spotify' else LAST_URL or 'https://www.youtube.com/'
        install_volume_hook(limited_volume(VOLUME))
        cdp('Page.navigate',{'url':destination})
        PROVIDER=source
        save_nonstop()
    except Exception:PROVIDER=previous;raise
    SPOTIFY_PENDING=0;WAKE_URL='';ERROR=''
    return status()


def spotify_dispatch(d):
    global SPOTIFY_URL,SPOTIFY_AD_FILTER,SPOTIFY_PENDING,MANUAL_PAUSE,VOLUME,ERROR
    action=d.get('action')
    if STANDBY:raise ValueError('Bật Media trước khi điều khiển Spotify')
    if action=='spotify_login':
        cdp('Page.navigate',{'url':spotify.LOGIN});SPOTIFY_PENDING=0
    elif action=='spotify_filter':
        enabled=d.get('enabled')
        if type(enabled) is not bool:raise ValueError('Lọc quảng cáo cần giá trị bật/tắt')
        previous=SPOTIFY_AD_FILTER;SPOTIFY_AD_FILTER=enabled
        try:save_nonstop()
        except Exception:SPOTIFY_AD_FILTER=previous;raise
        if not enabled and spotify.is_page(target().get('url')):spotify.ad_filter(evaluate,False,False)
    elif action=='play':
        destination=spotify.url(d.get('url'))
        spotify.track_metadata(destination)
        if POLICY.sleep_state()['expired']:
            VOLUME=POLICY.sleep['volume'];POLICY.cancel_sleep()
        install_volume_hook(limited_volume(VOLUME))
        cdp('Page.navigate',{'url':destination})
        SPOTIFY_URL=destination;MANUAL_PAUSE=False;SPOTIFY_PENDING=time.monotonic()+45
        save_nonstop()
    elif action in ('toggle','next','seek','volume'):
        if not spotify.is_page(target().get('url')):raise ValueError('Hoàn tất đăng nhập Spotify trên Pi trước')
        if action in ('toggle','next','seek'):SPOTIFY_PENDING=0
        if action=='toggle':
            if POLICY.sleep_state()['expired']:
                VOLUME=POLICY.sleep['volume'];POLICY.cancel_sleep();install_volume_hook(limited_volume(VOLUME))
            MANUAL_PAUSE=not status().get('paused',True)
        value=d.get('value')
        if action=='volume':
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:raise ValueError('Âm lượng phải từ 0 đến 100')
            value=limited_volume(value)
        spotify.control(evaluate,action,value)
        if action=='volume':VOLUME=value;install_volume_hook(value)
        if action in ('toggle','volume'):save_nonstop()
    else:raise ValueError('Spotify quản lý tính năng này trong Web Player; chọn playlist hoặc dùng YouTube')
    ERROR=''
    return status()


def spotify_tick():
    global SPOTIFY_PENDING,ERROR
    s=spotify_status()
    if SPOTIFY_PENDING and (time.monotonic()>SPOTIFY_PENDING or s.get('content_unavailable')):SPOTIFY_PENDING=0
    if not s.get('connected') or s.get('login_required') or s.get('content_unavailable'):
        SPOTIFY_AD_GUARD.reset()
        return
    ERROR=''
    volume_tick(s)
    if sleep_tick(s):
        SPOTIFY_AD_GUARD.reset()
        return
    if SPOTIFY_AD_GUARD.observe(s,blocked=MANUAL_PAUSE or BT_GUARD.summary().get('paused',False)):
        SPOTIFY_PENDING=0
        cdp('Page.reload',{'ignoreCache':False})
        return
    if MANUAL_PAUSE:SPOTIFY_PENDING=0
    if SPOTIFY_PENDING:
        if time.monotonic()>SPOTIFY_PENDING:SPOTIFY_PENDING=0
        else:
            try:matches=spotify.public_destination(target()['url'])==SPOTIFY_URL
            except ValueError:matches=False
            if matches:
                if s.get('url')==SPOTIFY_URL and s.get('track_matches') and not s.get('paused'):SPOTIFY_PENDING=0
                elif spotify.activate(evaluate,SPOTIFY_URL):SPOTIFY_PENDING=0
    spotify.ad_filter(evaluate,SPOTIFY_AD_FILTER,s.get('ad',False))


SAFETY_MUTE_JS="""(()=>{window.__piBluetoothHold=true;
if(!window.__piBluetoothMuted)window.__piBluetoothMuted=new Map();
const hold=v=>{if(!window.__piBluetoothHold||!(v instanceof HTMLMediaElement))return;
if(!window.__piBluetoothMuted.has(v))window.__piBluetoothMuted.set(v,v.muted);v.muted=true;v.pause()};
if(!window.__piBluetoothHoldInstalled){document.addEventListener('play',e=>hold(e.target),true);window.__piBluetoothHoldInstalled=true}
const elements=[...document.querySelectorAll('audio,video')];elements.forEach(hold);return elements.length})()"""
SAFETY_RELEASE_JS="""(()=>{window.__piBluetoothHold=false;
for(const [v,muted] of window.__piBluetoothMuted||[])v.muted=muted;
window.__piBluetoothMuted?.clear();return true})()"""


def hold_bluetooth():
    global GUARD_SCRIPT,GUARD_TARGET,MANUAL_PAUSE,SPOTIFY_PENDING,WAKE_URL,YOUTUBE_PENDING
    MANUAL_PAUSE=True;SPOTIFY_PENDING=0;WAKE_URL='';YOUTUBE_PENDING=None
    if STANDBY:return
    # Keep a hold across explicit source navigation too. No automatic resume.
    page=target()['id']
    if GUARD_TARGET and GUARD_TARGET!=page:GUARD_SCRIPT=None
    changed=GUARD_SCRIPT is None
    if GUARD_SCRIPT is None:
        GUARD_SCRIPT=cdp('Page.addScriptToEvaluateOnNewDocument',{'source':SAFETY_MUTE_JS})['identifier']
        GUARD_TARGET=page
    held=evaluate(SAFETY_MUTE_JS)
    if changed or not GUARD_FILE.exists():
        pending=GUARD_FILE.with_name(GUARD_FILE.name+'.'+str(time.monotonic_ns())+'.tmp')
        with pending.open('x') as stream:
            pending.chmod(0o600);json.dump(dict(script=GUARD_SCRIPT,target=GUARD_TARGET),stream)
        pending.replace(GUARD_FILE)
    if held==0 and PROVIDER=='spotify':
        # Spotify may own detached audio that DOM muting cannot reach. Closing
        # this dedicated browser is the bounded safety fallback for that case.
        set_power(False)
        BT_GUARD.message='Đã cho Media nghỉ vì không xác minh được việc tắt tiếng Spotify. Chọn đầu ra rồi bật Media hoặc phát một mục ghim.'
        return


def release_bluetooth():
    global GUARD_SCRIPT,GUARD_TARGET
    if not BT_GUARD.latched:return
    BT_GUARD.resume()
    try:
        if STANDBY:
            GUARD_SCRIPT=None;GUARD_TARGET='';GUARD_FILE.unlink(missing_ok=True);return
        if GUARD_SCRIPT:
            if not GUARD_TARGET or target()['id']==GUARD_TARGET:
                cdp('Page.removeScriptToEvaluateOnNewDocument',{'identifier':GUARD_SCRIPT})
            GUARD_SCRIPT=None
        evaluate(SAFETY_RELEASE_JS)
        GUARD_TARGET='';GUARD_FILE.unlink(missing_ok=True)
    except Exception:
        BT_GUARD.latched=True
        raise ValueError('Chưa bỏ được trạng thái tạm dừng an toàn; kiểm tra player trên Pi') from None


def load_bluetooth_hold():
    global GUARD_SCRIPT,GUARD_TARGET,MANUAL_PAUSE
    if not GUARD_FILE.exists():return
    info=GUARD_FILE.lstat()
    if GUARD_FILE.is_symlink() or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>4096:
        raise ValueError('Trạng thái bảo vệ Bluetooth không hợp lệ')
    data=json.loads(GUARD_FILE.read_text())
    if not all(isinstance(data.get(k),str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',data[k]) for k in ('script','target')):
        raise ValueError('Trạng thái bảo vệ Bluetooth không hợp lệ')
    GUARD_SCRIPT=data['script'];GUARD_TARGET=data['target'];BT_GUARD.latched=True;MANUAL_PAUSE=True
    BT_GUARD.message='Media đã tạm dừng để bảo vệ loa. Chọn đầu ra rồi bấm Phát để nghe tiếp.'


def bluetooth_loop():
    # Audio IPC may be slow; never hold the Media lock while waiting for it.
    while True:
        if (STANDBY and not BT_GUARD.latched) or not BT_GUARD.enabled:
            time.sleep(3);continue
        try:
            if modular():
                import audio_client
                snapshot=audio_client.call({'action':'status'},timeout=2)
            else:snapshot=audio_control.status()
        except Exception:snapshot=None
        with LOCK:
            BT_GUARD.observe(snapshot)
            if BT_GUARD.latched:
                try:hold_bluetooth()
                except Exception:pass  # Retry next tick; keep the stop latch.
        time.sleep(3)


def playlist_tick():
    global YOUTUBE_PENDING,LAST_URL
    if YOUTUBE_PENDING is None:return
    url,deadline=YOUTUBE_PENDING
    if time.monotonic()>deadline or MANUAL_PAUSE or POLICY.sleep_state()['expired'] or BT_GUARD.latched:
        YOUTUBE_PENDING=None;return
    page=target().get('url','')
    try:current=youtube_destination(page)
    except ValueError:return
    if urllib.parse.parse_qs(urllib.parse.urlsplit(current).query).get('list',[''])[0]!=YOUTUBE_LIST:return
    if '/watch?' in current:
        YOUTUBE_PENDING=None;return
    if current!=url:return
    candidate=evaluate("(()=>{const a=document.querySelector('ytd-playlist-video-renderer a#video-title[href],ytd-playlist-header-renderer a[href*=\"watch?\"]');return a?.href||''})()")
    try:
        value=youtube_destination(candidate)
        if urllib.parse.parse_qs(urllib.parse.urlsplit(value).query).get('list',[''])[0]!=YOUTUBE_LIST:return
        video=youtube_url(value)
    except ValueError:return
    if POLICY.reason(video.split('v=')[1],automatic=False):
        YOUTUBE_PENDING=None;raise ValueError('Bài đầu playlist đang bị chặn; chọn bài khác hoặc bỏ chặn')
    play(video);LAST_URL=video;YOUTUBE_PENDING=None


def play_destination(provider, value):
    """One navigation per explicit selection; cold browser work is deferred."""
    global PROVIDER,MANUAL_PAUSE,SPOTIFY_URL,WAKE_URL,WAKE_UNTIL,VOLUME,SPOTIFY_PENDING,YOUTUBE_PENDING
    value=destination(provider,value)
    if BT_GUARD.latched:release_bluetooth()
    before={}
    if POLICY.sleep_state()['expired']:
        VOLUME=POLICY.sleep['volume'];POLICY.cancel_sleep()
    if STANDBY:
        old_provider,old_pause,old_url=PROVIDER,MANUAL_PAUSE,SPOTIFY_URL
        PROVIDER=provider;MANUAL_PAUSE=False
        if provider=='spotify':SPOTIFY_URL=value
        try:set_power(True)
        except Exception:
            PROVIDER,MANUAL_PAUSE,SPOTIFY_URL=old_provider,old_pause,old_url
            raise
    else:
        if PROVIDER!=provider:
            try:
                if PROVIDER=='spotify':evaluate(spotify.PAUSE_JS);spotify.ad_filter(evaluate,False,False)
                else:evaluate('(()=>{const v=document.querySelector("video");if(v)v.pause();return true})()')
            except Exception:pass
            PROVIDER=provider
    MANUAL_PAUSE=False;SPOTIFY_PENDING=0;YOUTUBE_PENDING=None
    WAKE_URL=value;WAKE_UNTIL=time.monotonic()+45
    result=status()
    RECEIPT.begin('play',before,dict(provider=provider,url=value))
    result['command']=RECEIPT.observe(result)
    return result


def search_browser():
    """Explicit search may open a resting browser, without resuming old audio."""
    global STANDBY,MANUAL_PAUSE,WAKE_URL,SPOTIFY_PENDING,YOUTUBE_PENDING
    if not STANDBY:return
    old_pause=MANUAL_PAUSE
    STANDBY=False;MANUAL_PAUSE=True;WAKE_URL='';SPOTIFY_PENDING=0;YOUTUBE_PENDING=None
    try:open_browser();save_nonstop()
    except Exception:
        STANDBY=True;MANUAL_PAUSE=old_pause
        raise


def run_command(payload):
    """Track observed results without blocking an HTTP request waiting for playback."""
    action=payload.get('action','status')
    if action in ('apps','app_status','app_command'):return native_dispatch(payload)
    if action=='status':return status()
    if action=='catalog_status':return CATALOG.status()
    if action=='catalog_search':
        from media_catalog import query
        query(payload.get('provider'),payload.get('query'),payload.get('kind'))
        search_browser()
        return CATALOG.start(payload.get('provider'),payload.get('query'),payload.get('kind'))
    if action=='play':
        provider,value=link_destination(payload.get('url'))
        return play_destination(provider,value)
    if action in ('catalog_play','shortcut_play'):
        item=SHORTCUTS.get(payload.get('id')) if action=='shortcut_play' else payload
        return play_destination(item.get('provider'),item.get('url'))
    tracked=('play','shortcut_play','toggle','next','volume','seek','source','power','start')
    before=player_status() if action in tracked else {}
    expected={}
    if action in ('play','shortcut_play'):
        item=SHORTCUTS.get(payload.get('id')) if action=='shortcut_play' else dict(provider=PROVIDER,url=payload.get('url'))
        expected=dict(provider=item['provider'],url=destination(item['provider'],item['url']))
    elif action=='toggle':expected['paused']=not before.get('paused',True)
    elif action=='volume':
        value=payload.get('value')
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:raise ValueError('Âm lượng phải từ 0 đến 100')
        expected['volume']=limited_volume(value)
    elif action=='seek':
        value=payload.get('value')
        if type(value) not in (int,float) or value not in (-10,10):raise ValueError('Chỉ tua ±10 giây')
        expected['position']=max(0,min(before.get('duration') or 864000,before.get('position',0)+value))
    elif action=='source':expected['provider']=payload.get('provider')
    elif action in ('power','start'):expected['standby']=action=='power' and payload.get('enabled') is False
    if BT_GUARD.latched and (action in ('play','shortcut_play','toggle','start') or action=='power' and payload.get('enabled') is True):
        release_bluetooth()
    elif BT_GUARD.latched and action in ('next','seek'):
        raise ValueError('Loa đã ngắt; chọn đầu ra rồi bấm Phát trước')
    RECEIPT.receipt=None
    result=dispatch(payload)
    RECEIPT.begin(action,before,expected)
    result['command']=RECEIPT.observe(result)
    return result

def dispatch(d):
    global ERROR,END_LATCH,VOLUME,NONSTOP,MANUAL_PAUSE,LAST_URL,RECOVERY_AT,RECOVERY_COUNT,NONSTOP_NOTE,VOLUME_SCHEDULE,POLICY_NOTE,WAKE_URL,YOUTUBE_LIST,YOUTUBE_PENDING,YOUTUBE_QUALITY,QUALITY_AT
    action=d.get('action','status')
    if action=='audio':
        payload=d.get('payload')
        if not isinstance(payload,dict):raise ValueError('Yêu cầu âm thanh không hợp lệ')
        if modular():
            import audio_client
            return audio_client.call(payload)
        return audio_control.dispatch(payload)
    if action=='status':return status()
    if action=='youtube_quality':
        if d.get('value') not in youtube_quality.CHOICES:raise ValueError('Chất lượng YouTube không hợp lệ')
        previous=YOUTUBE_QUALITY;YOUTUBE_QUALITY=d['value']
        try:save_nonstop()
        except Exception:YOUTUBE_QUALITY=previous;raise
        QUALITY_AT=0
        return status()
    if action=='shortcut_save':
        source,value=link_destination(d.get('url'))
        SHORTCUTS.add(source,value,d.get('label'));return status()
    if action=='shortcut_remove':
        SHORTCUTS.remove(d.get('id'));return status()
    if action=='shortcut_play':
        item=SHORTCUTS.get(d.get('id'))
        if STANDBY:set_power(True)
        if PROVIDER!=item['provider']:select_source(item['provider'])
        WAKE_URL=''
        return dispatch(dict(action='play',url=item['url']))
    if action=='bluetooth_guard':
        if type(d.get('enabled')) is not bool:raise ValueError('Bảo vệ Bluetooth cần giá trị bật/tắt')
        previous=BT_GUARD.enabled;BT_GUARD.enabled=d['enabled']
        try:save_nonstop()
        except Exception:BT_GUARD.enabled=previous;raise
        return status()
    if action=='power':return set_power(d.get('enabled'))
    if action=='start':return set_power(True)
    if action=='source':return select_source(d.get('provider'))
    if PROVIDER=='spotify' and action not in ('sleep','sleep_cancel','volume_schedule'):
        return spotify_dispatch(d)
    if STANDBY and action in ('play','next','toggle','seek','volume','dislike'):
        raise ValueError('Media đang nghỉ; bấm Bật Media trước')
    if action in ('play','next','toggle'):WAKE_URL=''
    if action=='repeat':
        previous=POLICY.repeat.copy();POLICY.configure_repeat(d.get('setting'))
        try:save_nonstop()
        except Exception:POLICY.repeat=previous;raise
        return status()
    if action=='undislike':
        ident=d.get('id')
        if not isinstance(ident,str) or ident not in POLICY.disliked:raise ValueError('Không tìm thấy bài trong danh sách')
        title=POLICY.disliked.pop(ident)
        try:save_nonstop()
        except Exception:POLICY.disliked[ident]=title;raise
        return status()
    if action=='dislike':
        current=status()
        if not current.get('url') or not current.get('has_video') or current.get('ad'):raise ValueError('Chọn bài đang phát, ngoài thời gian quảng cáo')
        ident=current['url'].split('v=')[1];previous=POLICY.disliked.copy()
        POLICY.dislike(ident,current.get('title'));LAST_URL=current['url']
        try:save_nonstop()
        except Exception:POLICY.disliked=previous;raise
        try:move_next(status())
        except ValueError:
            evaluate(PAUSE_JS);MANUAL_PAUSE=True
            POLICY_NOTE='Đã ghi nhận không thích; chưa có bài phù hợp để chuyển'
        save_nonstop();return status()
    if action=='sleep':
        current=status()
        if not current.get('has_video'):raise ValueError('Mở một video trước khi hẹn giờ ngủ')
        old_sleep=POLICY.sleep;old_deadline=POLICY.deadline
        POLICY.start_sleep(d.get('minutes'),current.get('volume',VOLUME))
        if PROVIDER=='youtube':LAST_URL=current.get('url') or LAST_URL
        try:save_nonstop()
        except Exception:POLICY.sleep=old_sleep;POLICY.deadline=old_deadline;raise
        return status()
    if action=='sleep_cancel':
        if POLICY.sleep_state()['expired']:raise ValueError('Hẹn giờ đã kết thúc; bấm Phát để nghe tiếp')
        POLICY.cancel_sleep();save_nonstop();return status()
    if action=='volume_schedule':
        setting=validate_schedule(d.get('schedule'))
        previous=VOLUME_SCHEDULE
        VOLUME_SCHEDULE=setting
        try:save_nonstop()
        except Exception:VOLUME_SCHEDULE=previous;raise
        volume_tick(status())
        return status()
    if action=='nonstop':
        if type(d.get('enabled'))!=bool:raise ValueError('Nonstop cần giá trị bật/tắt')
        NONSTOP=d['enabled'];MANUAL_PAUSE=False;RECOVERY_AT=0;RECOVERY_COUNT=0
        current=status()
        if current.get('url'):LAST_URL=current['url']
        if current.get('has_video'):VOLUME=current.get('volume',VOLUME)
        NONSTOP_NOTE='Đang theo dõi' if NONSTOP else 'Đã tắt';save_nonstop();return status()
    if action in ('play','enqueue'):
        if action=='play':
            value=youtube_destination(d.get('url'))
            YOUTUBE_LIST=urllib.parse.parse_qs(urllib.parse.urlsplit(value).query).get('list',[''])[0]
            YOUTUBE_PENDING=None
            if '/playlist?' in value:
                if POLICY.sleep_state()['expired']:
                    VOLUME=POLICY.sleep['volume'];POLICY.cancel_sleep()
                install_volume_hook(limited_volume(VOLUME));cdp('Page.navigate',{'url':value})
                MANUAL_PAUSE=False;WAKE_URL='';YOUTUBE_PENDING=(value,time.monotonic()+45)
                return status()
        url=youtube_url(d.get('url'))
        if action=='enqueue':
            if len(QUEUE)>=50:raise ValueError('Hàng đợi tối đa 50 video')
            QUEUE.append(url)
        else:
            if POLICY.reason(url.split('v=')[1],automatic=False):raise ValueError('Bài này đang bị chặn; bỏ chặn trong danh sách Không thích trước')
            if POLICY.sleep_state()['expired']:
                VOLUME=POLICY.sleep['volume'];POLICY.cancel_sleep()
                MANUAL_PAUSE=False
                save_nonstop()
            play(url);LAST_URL=url;MANUAL_PAUSE=False
            if NONSTOP:save_nonstop()
    elif action=='clear':QUEUE.clear()
    elif action=='remove':
        index=d.get('index')
        if type(index)!=int or not 0<=index<len(QUEUE):raise ValueError('Mục hàng đợi không hợp lệ')
        QUEUE.pop(index)
    elif action=='next':
        move_next(status())
        if NONSTOP:save_nonstop()
    elif action in ('toggle','seek','volume'):
        if action=='toggle':
            if POLICY.sleep_state()['expired']:
                VOLUME=POLICY.sleep['volume']
                POLICY.cancel_sleep();MANUAL_PAUSE=False;save_nonstop()
                level=limited_volume(VOLUME);install_volume_hook(level)
                cmd=f'window.__piMediaVolume={level}/100;v.volume={level}/100;await v.play()'
            else:
                MANUAL_PAUSE=not status().get('paused',True)
                cmd='if(v.paused){await v.play()}else{v.pause()}'
            if NONSTOP:save_nonstop()
        else:
            n=d.get('value')
            if type(n) not in (int,float) or not math.isfinite(n):raise ValueError('Giá trị không hợp lệ')
            if action=='seek':
                if n not in (-10,10):raise ValueError('Chỉ tua ±10 giây')
                cmd=f'v.currentTime=Math.max(0,Math.min(Number.isFinite(v.duration)?v.duration:1e12,v.currentTime+({n})))'
            else:
                if not 0<=n<=100:raise ValueError('Âm lượng phải từ 0 đến 100')
                n=limited_volume(n)
                cmd=f'window.__piMediaVolume={n}/100;v.volume={n}/100;v.muted=false'
        evaluate('(async()=>{const v=document.querySelector("video");if(!v)throw Error("No video");'+cmd+';return true})()')
        if action=='volume':
            VOLUME=n
            install_volume_hook(n)
            if NONSTOP:save_nonstop()
    else:raise ValueError('Thao tác không được hỗ trợ')
    ERROR=''
    return status()

NONSTOP_JS="""(()=>{
const b=document.querySelector('.ytp-autonav-toggle-button');
if(b&&b.getAttribute('aria-checked')!=='true')b.click();
for(const dialog of document.querySelectorAll('yt-confirm-dialog-renderer,ytd-confirm-dialog-renderer')){
 const text=(dialog.textContent||'').toLowerCase();
 if(!/continue watching|video paused|tiếp tục xem|video.*tạm dừng/.test(text))continue;
 if(/sign in|đăng nhập|password|mật khẩu/.test(text))continue;
 const yes=[...dialog.querySelectorAll('button')].find(x=>x.offsetParent!==null&&/^(yes|continue|ok|có|tiếp tục)$/i.test(x.textContent.trim()));
 if(yes)yes.click();
}
const v=document.querySelector('video');if(v&&v.paused&&!v.ended)v.play().catch(()=>{});
return true;
})()"""

def nonstop_tick(s,now=None):
    global LAST_URL,LAST_PROGRESS,PROGRESS_AT,RECOVERY_AT,RECOVERY_COUNT,NONSTOP_NOTE
    if STANDBY or PROVIDER!='youtube':return
    now=time.monotonic() if now is None else now
    if POLICY.sleep_state()['expired']:NONSTOP_NOTE='Hết hẹn giờ ngủ; bấm Phát để nghe tiếp';return
    if not NONSTOP:return
    if MANUAL_PAUSE:NONSTOP_NOTE='Bạn đã tạm dừng; bấm Phát để tiếp tục';return
    if s.get('url'):LAST_URL=s['url']
    progress=(s.get('url'),round(s.get('position',0)))
    if s.get('has_video') and progress!=LAST_PROGRESS:
        LAST_PROGRESS=progress;PROGRESS_AT=now;RECOVERY_COUNT=0
    if now<RECOVERY_AT:return
    if s.get('connected') and s.get('has_video'):
        evaluate(NONSTOP_JS)
        NONSTOP_NOTE='Đang giữ Autoplay và tiếp tục phát'
        if s.get('ad'):return
        if s.get('ended'):
            if QUEUE:return
            move_next(s);RECOVERY_AT=now+20
            return
        if not s.get('notice') and (not PROGRESS_AT or now-PROGRESS_AT<180):return
    if not LAST_URL:NONSTOP_NOTE='Chọn một video đầu tiên để Nonstop tiếp tục';return
    RECOVERY_COUNT+=1
    RECOVERY_AT=now+min(900,60*2**min(RECOVERY_COUNT-1,4))
    NONSTOP_NOTE=f'Đang thử phục hồi · chờ {int(RECOVERY_AT-now)} giây trước lần tiếp'
    if POLICY.reason(LAST_URL.split('v=')[1],automatic=False):
        if s.get('up_next'):move_next(s)
        else:NONSTOP_NOTE='Bài phục hồi nằm trong danh sách không thích; chọn bài khác'
        return
    open_browser();play(youtube_url(LAST_URL));PROGRESS_AT=now

def fast_wake_loop():
    """Readiness polling only during a requested cold start, not while idle."""
    while True:
        time.sleep(.2 if WAKE_URL else .5)
        if not WAKE_URL or STANDBY or BT_GUARD.latched:continue
        try:
            # Wait for CDP without holding the player lock across startup.
            if not pages():continue
            with LOCK:
                if not BT_GUARD.latched:resume_tick()
        except Exception:pass


def advance_loop():
    global ERROR,END_LATCH,QUALITY_AT
    while True:
        time.sleep(3)
        with LOCK:
            if STANDBY:
                SPOTIFY_AD_GUARD.reset()
                continue
            if BT_GUARD.latched:
                SPOTIFY_AD_GUARD.reset()
                try:hold_bluetooth()
                except Exception:pass
                continue
            if PROVIDER=='spotify':
                try:resume_tick();spotify_tick()
                except Exception:ERROR='Chưa điều khiển được Spotify; kiểm tra Web Player trên Pi.'
                continue
            SPOTIFY_AD_GUARD.reset()
            if time.monotonic()-QUALITY_AT>=30:
                try:evaluate(youtube_quality.script(YOUTUBE_QUALITY));QUALITY_AT=time.monotonic()
                except Exception:pass
            if not WAKE_URL and not QUEUE and not NONSTOP and not VOLUME_SCHEDULE['enabled'] and not POLICY.sleep and not POLICY.repeat['enabled'] and not POLICY.disliked and YOUTUBE_PENDING is None:continue
            try:
                resume_tick()
                playlist_tick()
                s=status()
                if s.get('connected'):ERROR=''
                volume_tick(s)
                if sleep_tick(s):continue
                if preference_tick(s):continue
                nonstop_tick(s)
                if QUEUE and s.get('connected') and s.get('ended') and not s.get('ad') and not END_LATCH and not MANUAL_PAUSE:
                    END_LATCH=True
                    move_next(s)
            except Exception:ERROR=('Nonstop đang chờ thử lại; nếu có hộp thoại đăng nhập/keyring, xử lý trên Pi.' if NONSTOP else 'Chưa chuyển được bài tiếp theo; dùng nút Bài tiếp hoặc kiểm tra desktop.')

def native_dispatch(payload):
    action=payload.get('action')
    if action=='apps':return NATIVE.players()
    if action=='app_status':return NATIVE.status(payload.get('id'),payload.get('owner'))
    if action=='app_command':return NATIVE.command(payload.get('id'),payload.get('owner'),payload.get('command'),payload.get('value'))
    raise ValueError('Thao tác ứng dụng không hợp lệ.')


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(12)
        try:
            raw=self.rfile.readline(4097)
            if len(raw)>4096:raise ValueError('Yêu cầu quá dài')
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('Yêu cầu không hợp lệ')
            if data.get('action') in ('apps','app_status','app_command'):
                result=native_dispatch(data)  # Own lock; D-Bus never holds the browser policy lock.
            else:
                with LOCK:result=run_command(data)
            response={'ok':True,'data':result}
        except Exception as exc:response={'ok':False,'error':str(exc)[:200]}
        self.wfile.write(json.dumps(response).encode()+b'\n')

def main():
    load_nonstop()
    load_bluetooth_hold()
    path=Path(f'/run/user/{os.getuid()}/pi-media.sock')
    path.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(str(path),Handler) as server:
        path.chmod(0o600)
        threading.Thread(target=advance_loop,daemon=True).start()
        threading.Thread(target=bluetooth_loop,daemon=True).start()
        threading.Thread(target=fast_wake_loop,daemon=True).start()
        server.serve_forever()

if __name__=='__main__':main()
