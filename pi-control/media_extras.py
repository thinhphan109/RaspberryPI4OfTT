"""Explicit shortcut storage and RAM-only command/audio safety state."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import spotify_player


def youtube_destination(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Link YouTube không hợp lệ')
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or p.username or p.password or p.port is not None:
            raise ValueError()
        if p.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'):
            raise ValueError()
    except ValueError:
        raise ValueError('Chỉ nhận link HTTPS chính thức của YouTube') from None
    query = parse_qs(p.query)
    video = p.path.strip('/') if p.hostname == 'youtu.be' else query.get('v', [''])[0] if p.path == '/watch' else p.path.split('/')[2] if p.path.startswith(('/shorts/', '/live/')) else ''
    playlist = query.get('list', [''])[0]
    if playlist and not re.fullmatch(r'[A-Za-z0-9_-]{10,128}', playlist):
        raise ValueError('Mã playlist YouTube không hợp lệ')
    if video and re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        return 'https://www.youtube.com/watch?v='+video+('&list='+playlist if playlist else '')
    if p.hostname != 'youtu.be' and p.path == '/playlist' and playlist:
        return 'https://www.youtube.com/playlist?list='+playlist
    raise ValueError('Gửi link video hoặc playlist YouTube')


def destination(provider, value):
    if provider == 'youtube':
        return youtube_destination(value)
    if provider == 'spotify':
        result = spotify_player.url(value)
        if result == spotify_player.HOME:
            raise ValueError('Chọn bài hát, album hoặc playlist để ghim')
        return result
    raise ValueError('Nguồn phát không hợp lệ')


def link_destination(value):
    """Infer a supported provider from the pasted link, never the current tab."""
    if isinstance(value,str):
        value=value.strip()
        if value.startswith('spotify:'):return 'spotify',spotify_player.url(value)
        try:host=urlsplit(value).hostname
        except ValueError:host=None
        if host=='open.spotify.com':return 'spotify',destination('spotify',value)
    return 'youtube',destination('youtube',value)


class Shortcuts:
    def __init__(self, path):
        self.path = Path(path)
        self.items = None

    def rows(self):
        if self.items is None:
            if self.path.exists():
                if self.path.is_symlink() or self.path.stat().st_size > 128*1024:
                    raise ValueError('Không đọc được danh sách ghim an toàn')
                data = json.loads(self.path.read_text())
                if data.get('schema') != 1 or not isinstance(data.get('items'), list) or len(data['items']) > 24:
                    raise ValueError('Danh sách ghim không hợp lệ')
                checked = [self.entry(row.get('provider'), row.get('url'), row.get('label')) for row in data['items']]
                if len({row['id'] for row in checked}) != len(checked):
                    raise ValueError('Danh sách ghim có mục trùng')
                self.items = checked
            else:
                self.items = []
        return deepcopy(self.items)

    @staticmethod
    def entry(provider, url, label):
        url = destination(provider, url)
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 60 or any(ord(c) < 32 for c in label):
            raise ValueError('Tên ghim từ 1 đến 60 ký tự, không có ký tự điều khiển')
        return dict(id=hashlib.sha256((provider+':'+url).encode()).hexdigest()[:16],
                    provider=provider, url=url, label=label.strip())

    def save(self, items):
        if self.path.is_symlink():
            raise ValueError('Đường dẫn danh sách ghim không hợp lệ')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        pending = self.path.with_name(self.path.name+'.'+secrets.token_hex(4)+'.tmp')
        try:
            with pending.open('x', encoding='utf-8') as stream:
                pending.chmod(0o600)
                json.dump(dict(schema=1, items=items), stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            pending.replace(self.path)
            descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            pending.unlink(missing_ok=True)
        self.items = items

    def add(self, provider, url, label):
        row = self.entry(provider, url, label)
        items = self.rows()
        found = next((i for i, item in enumerate(items) if item['id'] == row['id']), None)
        if found is None:
            if len(items) >= 24:
                raise ValueError('Tối đa 24 mục ghim; bỏ một mục trước khi thêm')
            items.append(row)
        else:
            items[found] = row
        if items != self.items:
            self.save(items)

    def get(self, ident):
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{16}', ident):
            raise ValueError('Mục ghim không hợp lệ')
        row = next((row for row in self.rows() if row['id'] == ident), None)
        if row is None:
            raise ValueError('Mục ghim đã bị xóa; làm mới danh sách')
        return row

    def remove(self, ident):
        self.get(ident)
        self.save([row for row in self.rows() if row['id'] != ident])


class CommandReceipt:
    def __init__(self):
        self.receipt = None

    def begin(self, action, before, expected, now=None):
        self.before = deepcopy(before)
        self.expected = deepcopy(expected)
        self.play_sample = None
        self.deadline = (time.monotonic() if now is None else now)+(45 if action in ('play','shortcut_play','source','power','start') else 12)
        self.receipt = dict(id=secrets.token_hex(8), action=action, state='pending', message='Đang kiểm tra trạng thái phát…')

    @staticmethod
    def identity(state):
        return (state.get('url'), state.get('title'))

    def observe(self, state, now=None):
        if not self.receipt:
            return None
        if self.receipt['state'] != 'pending':
            return dict(self.receipt)
        action = self.receipt['action']
        expected = self.expected
        if action in ('play','shortcut_play') and state.get('content_unavailable'):
            self.receipt.update(state='unconfirmed',message=state.get('notice') or 'Nội dung không khả dụng trên Spotify.')
            return dict(self.receipt)
        ready = state.get('connected') and not state.get('login_required')
        playing = (ready and state.get('has_video') and state.get('paused') is False
                   and not any(state.get(key) for key in ('launch_pending','buffering','ad','ended')))
        confirmed = False
        if action in ('play','shortcut_play'):
            target = expected.get('url', '')
            matched = target in (state.get('context_url'), state.get('collection_url'), state.get('url'))
            if expected.get('provider')=='spotify' and '/track/' in target:
                matched=target==state.get('url') and state.get('track_matches') is True
            confirmed = playing and state.get('provider','youtube') == expected.get('provider') and matched
            if 'position_known' in state:
                position = state.get('position')
                valid = confirmed and state['position_known'] and type(position) in (int,float) and math.isfinite(position)
                sample = (self.identity(state), position) if valid else None
                previous = self.play_sample
                confirmed = bool(sample and previous and sample[0]==previous[0] and position>previous[1])
                if not sample or not previous or sample[0]!=previous[0] or position<previous[1]:
                    self.play_sample = sample
        elif action == 'toggle':
            confirmed = ready and state.get('has_video') and state.get('paused') is expected.get('paused')
        elif action == 'next':
            confirmed = playing and self.identity(state) != self.identity(self.before)
        elif action == 'volume':
            confirmed = ready and state.get('can_volume', True) and abs(state.get('volume', -999)-expected['volume']) <= 1
        elif action == 'seek':
            confirmed = ready and state.get('position_known', True) and abs(state.get('position', -999)-expected['position']) <= 4
        elif action == 'source':
            confirmed = ready and state.get('provider','youtube') == expected.get('provider')
        elif action in ('power','start'):
            confirmed = state.get('standby') is expected['standby'] and (expected['standby'] or ready)
        else:
            confirmed = True  # Non-playback actions completed synchronously.
        if confirmed:
            self.receipt.update(state='confirmed', message='Đã xác nhận trạng thái.' if action in ('play','shortcut_play','toggle','next','volume','seek','source','power','start') else 'Đã lưu thay đổi.')
        elif (time.monotonic() if now is None else now) >= self.deadline:
            message = ('Chưa thấy nội dung phát. Thử bấm Phát lại hoặc kiểm tra cửa sổ Media trên Pi.'
                       if action in ('play','shortcut_play') else
                       'Chưa xác nhận được thao tác. Kiểm tra trạng thái hoặc mở player trên Pi.')
            self.receipt.update(state='unconfirmed', message=message)
        return dict(self.receipt)


class BluetoothGuard:
    def __init__(self):
        self.enabled = True
        self.latched = False
        self.armed = ''
        self.snapshot = None
        self.checked_at = 0
        self.errors = 0
        self.message = ''

    def observe(self, snapshot, now=None):
        now = time.monotonic() if now is None else now
        if not self.enabled:
            return False
        if not isinstance(snapshot, dict) or snapshot.get('errors'):
            self.errors += 1
            lost = bool(self.armed) and self.errors >= 2
        else:
            self.errors = 0
            self.snapshot = deepcopy(snapshot)
            self.checked_at = now
            names = {row.get('name') for row in snapshot.get('devices', []) if row.get('kind') == 'output'}
            current = snapshot.get('defaults', {}).get('output', '')
            lost = bool(self.armed) and self.armed not in names
            if not lost:
                self.armed = current if current.startswith('bluez_output.') and current in names else ''
        if lost and not self.latched:
            self.latched = True
            self.message = 'Đã mất hoặc chưa xác minh được loa Bluetooth. Chọn đầu ra rồi bấm Phát để nghe tiếp.'
            return True
        return False

    def resume(self, now=None):
        if not self.latched:
            return
        if not self.enabled:
            self.latched = False
            self.message = ''
            return
        now = time.monotonic() if now is None else now
        data = self.snapshot or {}
        current = data.get('defaults', {}).get('output')
        outputs = [row.get('name') for row in data.get('devices', []) if row.get('kind') == 'output']
        if self.errors or now-self.checked_at > 8 or not current or current not in outputs:
            raise ValueError('Chưa xác minh được đầu ra âm thanh; chọn loa trong mục Âm thanh rồi thử lại')
        self.latched = False
        self.message = ''
        self.armed = current if current.startswith('bluez_output.') else ''

    def summary(self):
        return dict(enabled=self.enabled, paused=self.latched, watching=bool(self.armed), message=self.message)
