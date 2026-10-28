"""Fixed Spotify Web Player controls; no password, cookie or token handling."""
import math
import re
import json
import time
import urllib.request
from urllib.parse import urlsplit,parse_qs,urlencode

HOME = 'https://open.spotify.com/'
LOGIN = 'https://accounts.spotify.com/login?continue=https%3A%2F%2Fopen.spotify.com%2F'
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
TRACK_METADATA={}


def url(value):
    if not isinstance(value,str) or len(value)>2048:raise ValueError('Link Spotify không hợp lệ')
    if re.fullmatch(r'spotify:(?:track|album|playlist|artist|episode|show):[A-Za-z0-9]{22}',value):
        _,kind,ident=value.split(':');return HOME+kind+'/'+ident
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


def public_destination(value):
    """Spotify's logged-in track route redirects to album?highlight=spotify:track:ID."""
    canonical=url(value)
    highlight=parse_qs(urlsplit(value).query).get('highlight',[''])[0]
    if '/album/' in canonical and re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}',highlight):return url(highlight)
    return canonical


def track_metadata(value):
    """Public oEmbed title/art only, once on explicit play; never OAuth or embed HTML."""
    value=url(value)
    if '/track/' not in value:return None
    saved=TRACK_METADATA.get(value)
    if saved and time.monotonic()-saved[0]<600:return saved[1]
    result=dict(url=value,title='',art='')
    try:
        with HTTP.open('https://open.spotify.com/oembed?'+urlencode({'url':value}),timeout=3) as stream:
            raw=stream.read(65537)
            if len(raw)>65536:raise ValueError('Metadata too large')
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('Invalid public metadata')
        if isinstance(data.get('title'),str):result['title']=data['title'].strip()[:150]
        image=data.get('thumbnail_url','')
        match=re.search(r'/image/([a-fA-F0-9]{32,})',image) if isinstance(image,str) else None
        # Spotify image IDs encode size/crop in the prefix; the final 24 hex
        # characters identify the same artwork across 64/300/640px variants.
        if match:result['art']=match[1][-24:].lower()
    except (OSError,ValueError,TypeError):pass
    TRACK_METADATA[value]=(time.monotonic(),result)
    while len(TRACK_METADATA)>24:TRACK_METADATA.pop(next(iter(TRACK_METADATA)))
    return result


def state_script(value):
    # Reads only cached public metadata; a status request never performs HTTP.
    cached=TRACK_METADATA.get(value)
    expected=cached[1] if cached else None
    return '(()=>{const PI_EXPECTED='+json.dumps(expected)+';return '+STATE_JS+';})()'


def state(raw):
    if not isinstance(raw,dict):raise ValueError('Chưa đọc được Spotify')
    result={k:str(raw.get(k) or '')[:300] for k in ('title','artist','notice')}
    for key in ('has_video','paused','ad','ad_muted','login_required','can_seek','can_next','can_toggle','can_volume','position_known','playback_observed','content_unavailable','track_matches'):
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
    if result['content_unavailable']:
        result.update(notice='Spotify báo nội dung không khả dụng: link có thể đã bị xoá, đặt riêng tư hoặc giới hạn khu vực.',has_video=False,can_toggle=False,can_next=False,can_seek=False)
    return result


STATE_JS=r"""(()=>{
const visible=e=>!!e&&e.getClientRects().length>0;
const v=document.querySelector('audio')||document.querySelector('video');
const button=document.querySelector('[data-testid="control-button-playpause"],[data-testid="play-pause-button"]');
const info=document.querySelector('[data-testid="now-playing-widget-v2"],[data-testid="now-playing-widget"]');
const link=info?.querySelector('a[data-testid="context-item-link"],a[href*="/track/"],a[href*="/episode/"]');
const meta=navigator.mediaSession?.metadata;
const currentTitle=(link?.textContent||info?.querySelector('a[href*="/album/"]')?.textContent||meta?.title||'Spotify').trim();
const currentArtist=meta?.artist||'';
const path=location.pathname||location.href.split('spotify.com')[1]||'';
const highlighted=decodeURIComponent((location.href.match(/[?&]highlight=([^&#]+)/)||[])[1]||'').match(/^spotify:track:([A-Za-z0-9]{22})$/)?.[1];
const requested=path.match(/^\/(?:intl-[^/]+\/)?track\/([A-Za-z0-9]{22})/)?.[1]||highlighted;
const norm=s=>(s||'').normalize('NFKC').trim().toLowerCase();
const row=requested?[...document.querySelectorAll('main [data-testid="tracklist-row"]')].find(r=>[...r.querySelectorAll('a[href]')].some(a=>a.href.split('?')[0].endsWith('/track/'+requested))):null;
const expectedLink=row?[...row.querySelectorAll('a[href]')].find(a=>a.href.split('?')[0].endsWith('/track/'+requested)):null;
const expectedTitle=expectedLink?.textContent||document.querySelector('main h1')?.textContent||'';
const artists=[...row?.querySelectorAll('a[href*="/artist/"]')||[]].map(a=>a.textContent);
const expected=typeof PI_EXPECTED==='undefined'?null:PI_EXPECTED;
const artwork=meta?.artwork?.[0]?.src||info?.querySelector('img')?.src||'';
const art=(artwork.match(/\/image\/([a-fA-F0-9]{32,})/)||[])[1]?.slice(-24).toLowerCase();
const metadataMatch=!!requested&&!!expected?.title&&expected.url.endsWith('/track/'+requested)&&norm(expected.title)===norm(currentTitle)&&(!art||!expected.art||art===expected.art);
const matches=metadataMatch||!!requested&&(link?.href?.split('?')[0].endsWith('/track/'+requested)||!!expectedTitle&&norm(expectedTitle)===norm(currentTitle)&&(!artists.length||artists.some(a=>norm(currentArtist).includes(norm(a)))));
const login=[...document.querySelectorAll('[data-testid="login-button"],a[href*="accounts.spotify.com/login"]')].some(visible);
const ad=[...document.querySelectorAll('[data-testid="ad-label"],[data-testid="audio-ad"],[data-testid="track-info-advertiser"]')].some(visible)||(/^(advertisement|quảng cáo)$/i.test(meta?.title||'')&&/^spotify$/i.test(meta?.artist||''));
const text=(document.querySelector('[role="alert"]')?.textContent||'').trim();
const pageText=(document.querySelector('main')?.innerText||'').slice(0,2500);
const unavailable=/this (playlist|track|album|song) is not available|owner of this playlist has made it private|couldn.t find that (playlist|track|album)|không (có sẵn|khả dụng)|đã (bị )?xoá/i.test(pageText);
const clock=selector=>{const value=document.querySelector(selector)?.textContent?.trim();if(!value||!/^\d{1,3}:\d{2}(?::\d{2})?$/.test(value))return null;return value.split(':').reduce((total,n)=>total*60+Number(n),0)};
const position=clock('[data-testid="playback-position"]'),duration=clock('[data-testid="playback-duration"]');
const sameMedia=!!v&&(duration===null||Number.isFinite(v.duration)&&Math.abs(v.duration-duration)<3);
const label=button?.getAttribute('aria-label')||'';
const paused=/pause|tạm dừng/i.test(label)?false:/play|phát/i.test(label)?true:v?v.paused:true;
return {title:currentTitle,artist:currentArtist,url:location.href,track_url:metadataMatch?expected.url:link?.href||'',track_matches:!!matches,
artwork,has_video:!!v||(visible(button)&&!!(link||meta?.title)),paused,content_unavailable:unavailable,
position:position??(sameMedia?v.currentTime:0),duration:duration??(sameMedia?v.duration:0),volume:sameMedia?Math.round(v.volume*100):0,login_required:login,ad,ad_muted:ad&&!!window.__piSpotifyAdMute,
can_seek:sameMedia&&Number.isFinite(v.duration)&&v.duration>0,can_next:!!document.querySelector('[data-testid="control-button-skip-forward"]:not(:disabled)'),can_toggle:visible(button)&&!button.disabled&&!!(v||link||meta?.title),
can_volume:sameMedia,position_known:position!==null||sameMedia&&Number.isFinite(v.currentTime),playback_observed:sameMedia,
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


def activate(evaluate, destination=None):
    target=url(destination) if destination else HOME
    metadata=TRACK_METADATA.get(target)
    title=metadata[1].get('title','') if metadata else ''
    return evaluate(r"""(()=>{const target=TARGET,title=TITLE,main=document.querySelector('main');if(!main)return false;
if(target.includes('/track/')){
 const id=new URL(target).pathname.split('/').pop();
 const labelMatch=r=>{const label=(r.querySelector('button')?.getAttribute('aria-label')||'').toLowerCase();return !!title&&['play ','pause ','phát ','tạm dừng '].some(p=>label.startsWith(p+title.toLowerCase()+' by ')||label.startsWith(p+title.toLowerCase()+' của '))};
 const row=[...main.querySelectorAll('[data-testid="tracklist-row"]')].find(r=>[...r.querySelectorAll('a[href]')].some(a=>a.href.split('?')[0].endsWith('/track/'+id))||labelMatch(r));
 if(row){const b=row.querySelector('button[data-testid="play-button"],button[data-testid="track-row-play-pause-button"]')||(labelMatch(row)?row.querySelector('button'):null);
 if(b&&!b.disabled){if(!/pause|tạm dừng/i.test(b.getAttribute('aria-label')||''))b.click();return true}
 row.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));return true;}
 if(!location.pathname.includes('/track/'+id))return false;
}
const b=main.querySelector('[data-testid="play-button"]');
if(!b||b.disabled||!b.getClientRects().length)return false;if(!/pause|tạm dừng/i.test(b.getAttribute('aria-label')||''))b.click();return true})()""".replace('const target=TARGET,title=TITLE','const target='+json.dumps(target)+',title='+json.dumps(title),1))
