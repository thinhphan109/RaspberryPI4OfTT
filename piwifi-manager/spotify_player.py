"""Fixed Spotify Web Player controls; no password, cookie or token handling."""
import math
import re
from urllib.parse import urlsplit

HOME = 'https://open.spotify.com/'
LOGIN = 'https://accounts.spotify.com/login?continue=https%3A%2F%2Fopen.spotify.com%2F'


def url(value):
    if not isinstance(value,str) or len(value)>2048:raise ValueError('Link Spotify không hợp lệ')
    try:p=urlsplit(value)
    except ValueError:raise ValueError('Link Spotify không hợp lệ') from None
    if p.scheme!='https' or p.hostname!='open.spotify.com' or p.username or p.password or p.port is not None:
        raise ValueError('Chỉ nhận link HTTPS open.spotify.com')
    path=re.sub(r'^/intl-[a-z]{2}(?:-[a-z]{2})?(?=/)', '', p.path, flags=re.I)
    if path in ('','/'):return HOME
    if not re.fullmatch(r'/(?:track|album|playlist|artist|episode|show)/[A-Za-z0-9]{22}/?',path):
        raise ValueError('Gửi link bài hát, album, playlist, nghệ sĩ hoặc podcast Spotify')
    return HOME.rstrip('/')+path.rstrip('/')


def is_page(value, auth=False):
    try:
        p=urlsplit(value)
        return p.scheme=='https' and not p.username and not p.password and p.port is None and p.hostname in (('open.spotify.com','accounts.spotify.com') if auth else ('open.spotify.com',))
    except (ValueError,TypeError):return False


def state(raw):
    if not isinstance(raw,dict):raise ValueError('Chưa đọc được Spotify')
    result={k:str(raw.get(k) or '')[:300] for k in ('title','artist','notice')}
    for key in ('has_video','paused','ad','ad_muted','login_required','can_seek','can_next','can_toggle','can_volume','position_known','playback_observed'):
        result[key]=raw.get(key) is True
    for key,maximum in (('position',864000),('duration',864000),('volume',100)):
        value=raw.get(key,0)
        result[key]=max(0,min(maximum,value)) if type(value) in (int,float) and math.isfinite(value) else 0
    try:result['url']=url(raw.get('track_url') or raw.get('url'))
    except ValueError:result['url']=''
    artwork=raw.get('artwork','')
    result['artwork']=artwork if isinstance(artwork,str) and len(artwork)<2048 and re.fullmatch(r'https://i\.scdn\.co/image/[a-fA-F0-9]+',artwork) else ''
    if result['login_required']:
        result['notice']='Đăng nhập Spotify trực tiếp trong cửa sổ Media trên Pi.'
        result['has_video']=False
    return result


STATE_JS=r"""(()=>{
const visible=e=>!!e&&e.getClientRects().length>0;
const v=document.querySelector('audio')||document.querySelector('video');
const button=document.querySelector('[data-testid="control-button-playpause"],[data-testid="play-pause-button"]');
const info=document.querySelector('[data-testid="now-playing-widget"]');
const link=info?.querySelector('a[data-testid="context-item-link"],a[href*="/track/"],a[href*="/episode/"]');
const meta=navigator.mediaSession?.metadata;
const login=[...document.querySelectorAll('[data-testid="login-button"],a[href*="accounts.spotify.com/login"]')].some(visible);
const ad=[...document.querySelectorAll('[data-testid="ad-label"],[data-testid="audio-ad"],[data-testid="track-info-advertiser"]')].some(visible)||(/^(advertisement|quảng cáo)$/i.test(meta?.title||'')&&/^spotify$/i.test(meta?.artist||''));
const text=(document.querySelector('[role="alert"]')?.textContent||'').trim();
return {title:(link?.textContent||meta?.title||'Spotify').trim(),artist:meta?.artist||'',url:location.href,track_url:link?.href||'',
artwork:meta?.artwork?.[0]?.src||info?.querySelector('img')?.src||'',has_video:!!v||(visible(button)&&!!(link||meta?.title)),paused:v?v.paused:!(/pause|tạm dừng/i.test(button?.getAttribute('aria-label')||'')),
position:v?.currentTime||0,duration:v?.duration||0,volume:v?Math.round(v.volume*100):0,login_required:login,ad,ad_muted:ad&&!!window.__piSpotifyAdMute,
can_seek:!!v&&Number.isFinite(v.duration)&&v.duration>0,can_next:!!document.querySelector('[data-testid="control-button-skip-forward"]:not(:disabled)'),can_toggle:visible(button)&&!button.disabled&&!!(v||link||meta?.title),
can_volume:!!v,position_known:!!v&&Number.isFinite(v.currentTime),playback_observed:!!v,
notice:/protected content|widevine|DRM/i.test(text)?'Spotify chưa phát được nội dung bảo vệ; kiểm tra Widevine trên Pi.':v?.error?'Spotify báo lỗi phát; kiểm tra cửa sổ trên Pi.':''};})()"""

PAUSE_JS=r"""(()=>{const v=document.querySelector('audio')||document.querySelector('video');
const b=document.querySelector('[data-testid="control-button-playpause"],[data-testid="play-pause-button"]');
if(b&&/pause|tạm dừng/i.test(b.getAttribute('aria-label')||''))b.click();else if(v)v.pause();return true})()"""


def control(evaluate, action, value=None):
    if action=='next':
        expression="const b=document.querySelector('[data-testid=\"control-button-skip-forward\"]');if(!b||b.disabled)throw Error('Skip unavailable');b.click()"
    elif action=='toggle':
        expression="const b=document.querySelector('[data-testid=\"control-button-playpause\"],[data-testid=\"play-pause-button\"]');if(!b||b.disabled)throw Error('Player unavailable');b.click()"
    elif action=='seek':
        if value not in (-10,10) or type(value) not in (int,float):raise ValueError('Chỉ tua ±10 giây')
        expression=f"const v=document.querySelector('audio')||document.querySelector('video');if(!v||!Number.isFinite(v.duration))throw Error('Seek unavailable');v.currentTime=Math.max(0,Math.min(v.duration,v.currentTime+({value})))"
    elif action=='volume':
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:raise ValueError('Âm lượng phải từ 0 đến 100')
        expression=f"const v=document.querySelector('audio')||document.querySelector('video');if(!v)throw Error('Player unavailable');window.__piMediaVolume={value}/100;v.volume={value}/100;if(!window.__piSpotifyAdMute)v.muted=false;else window.__piSpotifyAdMute.muted=false"
    else:raise ValueError('Thao tác Spotify không được hỗ trợ')
    return evaluate('(()=>{'+expression+';return true})()')


def ad_filter(evaluate, enabled, detected):
    # Mute only explicit ad signals. Never fast-forward/reload or change DRM.
    if enabled and detected:
        return evaluate("(()=>{const v=document.querySelector('audio')||document.querySelector('video');if(!v)return false;const s=window.__piSpotifyAdMute;if(s&&s.element!==v){s.element.muted=s.muted;delete window.__piSpotifyAdMute}if(!window.__piSpotifyAdMute)window.__piSpotifyAdMute={element:v,muted:v.muted};v.muted=true;return true})()")
    return evaluate("(()=>{const s=window.__piSpotifyAdMute;if(s){s.element.muted=s.muted;delete window.__piSpotifyAdMute}return true})()")


def activate(evaluate):
    return evaluate(r"""(()=>{const b=document.querySelector('main [data-testid="play-button"],[data-testid="main-view"] [data-testid="play-button"]');
if(!b||b.disabled||!b.getClientRects().length)return false;if(!/pause|tạm dừng/i.test(b.getAttribute('aria-label')||''))b.click();return true})()""")
