"""Explicit, bounded browser search. Reads public result cards, never account data."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from urllib.parse import quote, urlencode, urlsplit
import urllib.request
import websocket

from media_extras import destination

PORT = 18769
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SPOTIFY_JS = r"""(()=>{const main=document.querySelector('main');if(!main)return {};
const parts=location.pathname.split('/'),query=decodeURIComponent(parts[2]||''),kind=parts[3]||'all';
const visible=e=>!!e&&e.getClientRects().length>0;
const loading=[...main.querySelectorAll('[data-testid="loading-page"],[data-testid="loadingIcon"]')].some(visible);
const scope=kind==='tracks'?main.querySelector('[data-testid="track-list"]'):main;
const login=!!main.querySelector('[data-testid="login-button"]');const rows=[];
for(const a of scope?.querySelectorAll('a[href]')||[]){
 if(a.closest('footer,nav,aside,[data-testid="footer-div"],[data-testid="carousel-scroller"]'))continue;
 if(kind==='tracks'&&!/\/track\//.test(a.href)||kind==='playlists'&&!/\/playlist\//.test(a.href))continue;
 if(!/\/(track|album|playlist|artist|episode|show)\/[A-Za-z0-9]{22}(?:\?|$|\/)/.test(a.href)||!a.getClientRects().length)continue;
 const card=a.closest('[data-testid="tracklist-row"],[data-testid="card"],[role="row"],section li')||a.parentElement;
 const title=(a.textContent||a.getAttribute('aria-label')||card?.querySelector('img')?.alt||'').trim();
 if(title)rows.push({url:a.href,title,subtitle:(card?.innerText||'').trim().slice(0,180)});
 if(rows.length>=40)break;
}return {rows,login,ready:!loading&&!!scope,query,kind};})()"""

YOUTUBE_JS = r"""(()=>{const rows=[];for(const card of document.querySelectorAll('ytd-video-renderer,yt-lockup-view-model')){
 const a=card.querySelector('a#video-title,a.yt-lockup-metadata-view-model__title,a.ytLockupMetadataViewModelTitle');if(a)rows.push({url:a.href,title:a.textContent.trim(),subtitle:card.querySelector('#channel-name,.yt-content-metadata-view-model')?.textContent?.trim()||''});
 if(rows.length>=12)break;
}return {rows,ready:location.pathname==='/results',query:new URL(location.href).searchParams.get('search_query')};})()"""


def query(provider, value, kind=None):
    if provider not in ('spotify', 'youtube'):
        raise ValueError('Nguồn tìm kiếm không hợp lệ')
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120 or any(ord(c) < 32 for c in value):
        raise ValueError('Nhập từ khóa từ 1 đến 120 ký tự')
    value = value.strip()
    kind=search_kind(provider,kind)
    url = ('https://open.spotify.com/search/'+quote(value, safe='')+('/'+kind if kind!='all' else '') if provider == 'spotify'
           else 'https://www.youtube.com/results?'+urlencode({'search_query': value}))
    return value, url


def search_kind(provider,kind=None):
    if kind is None:return 'tracks' if provider=='spotify' else 'videos'
    if kind not in (('tracks','playlists','all') if provider=='spotify' else ('videos',)):
        raise ValueError('Loại tìm kiếm không hợp lệ')
    return kind


def search_ready(provider,value,kind,raw):
    return isinstance(raw,dict) and raw.get('ready') is True and raw.get('query')==value and (provider!='spotify' or raw.get('kind')==kind)


def is_search(value):
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and not p.username and not p.password and p.port is None and (
            p.hostname == 'open.spotify.com' and p.path.startswith('/search/') or
            p.hostname == 'www.youtube.com' and p.path == '/results')
    except (TypeError, ValueError):
        return False


def results(provider, raw):
    rows, seen = [], set()
    for item in (raw.get('rows') or [])[:40]:
        if not isinstance(item, dict):
            continue
        try:
            url = destination(provider, item.get('url'))
        except ValueError:
            continue
        title = str(item.get('title') or '').strip()[:150]
        if not title or url in seen:
            continue
        seen.add(url)
        rows.append(dict(url=url, title=title, subtitle=' '.join(str(item.get('subtitle') or '').split())[:180], provider=provider))
        if len(rows) == 12:
            break
    return rows


class Connection:
    def __init__(self, url):
        if not url.startswith(f'ws://127.0.0.1:{PORT}/'):
            raise ValueError('Invalid local browser endpoint')
        self.socket = websocket.create_connection(url, timeout=2, suppress_origin=True)
        self.sequence = 0

    def call(self, method, params=None):
        self.sequence += 1
        self.socket.send(json.dumps(dict(id=self.sequence, method=method, params=params or {})))
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            raw = self.socket.recv()
            if len(raw) > 512*1024:
                raise ValueError('Browser response too large')
            data = json.loads(raw)
            if data.get('id') == self.sequence:
                if data.get('error'):
                    raise ValueError('Browser command failed')
                return data.get('result', {})
        raise TimeoutError('Browser response timed out')

    def close(self):
        self.socket.close()


class Catalog:
    def __init__(self, ledger):
        self.lock = threading.Lock()
        self.ledger = Path(ledger)
        self.owned = set()
        self.cache = {}
        self.state = dict(running=False, rows=[], message='', provider='spotify', query='', revision=0)

    def status(self):
        with self.lock:
            return deepcopy(self.state)

    def start(self, provider, value, kind=None):
        kind=search_kind(provider,kind)
        value, url = query(provider, value,kind)
        with self.lock:
            if self.state['running']:
                raise ValueError('Đang tìm kiếm; chờ hoàn tất trước khi tìm tiếp')
            cached = self.cache.get((provider, value,kind))
            if cached and time.monotonic()-cached[0] >= 300:
                self.cache.pop((provider,value,kind))
                cached = None
            self.state.update(running=not bool(cached),
                              rows=deepcopy(cached[1]) if cached else [], message='Đang tìm trên Pi…',
                              provider=provider, query=value, kind=kind,revision=self.state['revision']+1)
            if not self.state['running']:
                self.state['message']='Kết quả đã lưu tạm'
            else:
                threading.Thread(target=self.worker, args=(provider, value, url,kind), daemon=True).start()
            return deepcopy(self.state)

    def browser(self):
        with HTTP.open(f'http://127.0.0.1:{PORT}/json/version', timeout=2) as stream:
            return Connection(json.load(stream)['webSocketDebuggerUrl'])

    def recover(self):
        """Close only a previous search tab recorded in private tmpfs."""
        try:
            if self.ledger.is_symlink() or self.ledger.stat().st_size > 4096:
                return
            ident = json.loads(self.ledger.read_text()).get('id')
            browser = self.browser()
            try:
                rows = browser.call('Target.getTargets').get('targetInfos', [])
                if any(p.get('targetId') == ident and (is_search(p.get('url')) or p.get('url') == 'about:blank') for p in rows):
                    browser.call('Target.closeTarget', {'targetId': ident})
                self.ledger.unlink(missing_ok=True)
            finally:
                browser.close()
        except (OSError, ValueError, KeyError, websocket.WebSocketException):
            pass

    def worker(self, provider, value, url,kind=None):
        browser = page = None
        ident = None
        rows = []
        message = ''
        try:
            kind=search_kind(provider,kind)
            self.recover()
            ready_until=time.monotonic()+8
            while True:
                try:browser = self.browser();break
                except (OSError,ValueError,websocket.WebSocketException):
                    if time.monotonic()>=ready_until:raise
                    time.sleep(.2)
            ident = browser.call('Target.createTarget', {'url':'about:blank', 'background':True})['targetId']
            with self.lock:
                self.owned.add(ident)
            self.ledger.write_text(json.dumps({'id':ident}))
            self.ledger.chmod(0o600)
            page = Connection(f'ws://127.0.0.1:{PORT}/devtools/page/{ident}')
            page.call('Page.addScriptToEvaluateOnNewDocument', {'source':"HTMLMediaElement.prototype.play=function(){return Promise.resolve()};document.addEventListener('play',e=>{if(e.target instanceof HTMLMediaElement)e.target.pause()},true)"})
            page.call('Network.enable')
            page.call('Network.setBlockedURLs', {'urls':['*.jpg','*.jpeg','*.png','*.webp','*.woff2']})
            page.call('Page.navigate', {'url':url})
            deadline = time.monotonic()+35
            first_rows_at=None
            changed_at=time.monotonic()
            while time.monotonic() < deadline:
                try:
                    result = page.call('Runtime.evaluate', {'expression':SPOTIFY_JS if provider == 'spotify' else YOUTUBE_JS, 'returnByValue':True})
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    # Chromium can spend several seconds compiling a cold site.
                    # Keep the same bounded job and ignore late response IDs.
                    continue
                raw = result.get('result', {}).get('value') or {}
                if not search_ready(provider,value,kind,raw):
                    time.sleep(.4);continue
                found = results(provider, raw)
                if found and found!=rows:
                    rows=found
                    changed_at=time.monotonic()
                    with self.lock:
                        self.state.update(rows=deepcopy(rows),
                                          message=f'Đã tìm thấy {len(rows)} kết quả · đang kiểm tra thêm…')
                if rows:
                    if first_rows_at is None:first_rows_at=time.monotonic()
                    if len(rows)>=12 or time.monotonic()-first_rows_at>=3 and time.monotonic()-changed_at>=1.2:break
                time.sleep(.6)
            message = f'{len(rows)} kết quả · phát trên loa của Pi' if rows else 'Chưa có kết quả. Kiểm tra đăng nhập, kết nối hoặc thử từ khóa khác trên Pi.'
            if rows:
                with self.lock:
                    self.cache[(provider,value,kind)] = (time.monotonic(),deepcopy(rows))
                    while len(self.cache) > 8:
                        self.cache.pop(next(iter(self.cache)))
        except Exception:
            message = 'Không đọc được tìm kiếm từ trình duyệt Pi. Thử lại hoặc dùng link trực tiếp.'
        finally:
            if page:
                page.close()
            closed = ident is None
            if browser:
                try:
                    if ident:
                        closed = browser.call('Target.closeTarget', {'targetId':ident}).get('success') is True
                except Exception:
                    pass
                browser.close()
            with self.lock:
                if closed:
                    self.owned.discard(ident)
                    try:self.ledger.unlink(missing_ok=True)
                    except OSError:pass
                self.state.update(running=False, rows=rows, message=message)
