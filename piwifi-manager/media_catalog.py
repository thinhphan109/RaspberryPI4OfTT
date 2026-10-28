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
const login=!!main.querySelector('[data-testid="login-button"]');const rows=[];
for(const a of main.querySelectorAll('a[href]')){
 if(!/\/(track|album|playlist|artist|episode|show)\/[A-Za-z0-9]{22}(?:\?|$|\/)/.test(a.href)||!a.getClientRects().length)continue;
 const card=a.closest('[data-testid="tracklist-row"],[data-testid="card"],[role="row"],section li')||a.parentElement;
 const title=(a.textContent||a.getAttribute('aria-label')||card?.querySelector('img')?.alt||'').trim();
 if(title)rows.push({url:a.href,title,subtitle:(card?.innerText||'').trim().slice(0,180)});
 if(rows.length>=40)break;
}return {rows,login};})()"""

YOUTUBE_JS = r"""(()=>{const rows=[];for(const card of document.querySelectorAll('ytd-video-renderer')){
 const a=card.querySelector('a#video-title');if(a)rows.push({url:a.href,title:a.textContent.trim(),subtitle:card.querySelector('#channel-name')?.textContent?.trim()||''});
 if(rows.length>=12)break;
}return {rows};})()"""


def query(provider, value):
    if provider not in ('spotify', 'youtube'):
        raise ValueError('Nguồn tìm kiếm không hợp lệ')
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120 or any(ord(c) < 32 for c in value):
        raise ValueError('Nhập từ khóa từ 1 đến 120 ký tự')
    value = value.strip()
    url = ('https://open.spotify.com/search/'+quote(value, safe='') if provider == 'spotify'
           else 'https://www.youtube.com/results?'+urlencode({'search_query': value}))
    return value, url


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
        rows.append(dict(url=url, title=title, subtitle=str(item.get('subtitle') or '')[:180], provider=provider))
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
        raise ValueError('Browser response timed out')

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

    def start(self, provider, value):
        value, url = query(provider, value)
        with self.lock:
            if self.state['running']:
                raise ValueError('Đang tìm kiếm; chờ hoàn tất trước khi tìm tiếp')
            cached = self.cache.get((provider, value))
            self.state.update(running=not bool(cached and time.monotonic()-cached[0] < 300),
                              rows=deepcopy(cached[1]) if cached else [], message='Đang tìm trên Pi…',
                              provider=provider, query=value, revision=self.state['revision']+1)
            if not self.state['running']:
                self.state['message']='Kết quả đã lưu tạm'
            else:
                threading.Thread(target=self.worker, args=(provider, value, url), daemon=True).start()
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

    def worker(self, provider, value, url):
        browser = page = None
        ident = None
        rows = []
        message = ''
        try:
            self.recover()
            browser = self.browser()
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
            deadline = time.monotonic()+22
            while time.monotonic() < deadline:
                result = page.call('Runtime.evaluate', {'expression':SPOTIFY_JS if provider == 'spotify' else YOUTUBE_JS, 'returnByValue':True})
                raw = result.get('result', {}).get('value') or {}
                rows = results(provider, raw)
                if rows:
                    break
                time.sleep(.6)
            message = f'{len(rows)} kết quả · phát trên loa của Pi' if rows else 'Chưa có kết quả. Kiểm tra đăng nhập, kết nối hoặc thử từ khóa khác trên Pi.'
            if rows:
                with self.lock:
                    self.cache[(provider,value)] = (time.monotonic(),deepcopy(rows))
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
