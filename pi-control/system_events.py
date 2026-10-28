"""Selected system events, bounded in RAM and checkpointed only after changes.

Never executes messages, changes a mount or keeps a camera viewer alive.
"""
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import socket
import subprocess
import threading
import time
from runtime_config import unit, desktop_runtime, modular

LIMIT = 2000
MAX_BYTES = 3 * 1024 * 1024
RETENTION = 30 * 86400
GROUPING_VERSION = 2
UNITS = ('NetworkManager.service', 'piwifi-web.service', 'piwifi-observer.service',
         'piwifi-guard.service', 'adguardhome.service', 'cloudflared.service')
USER_UNITS = ('pi-camera.service', 'pi-media.service', 'pi-media-browser.service')
if modular():
    UNITS=tuple(dict.fromkeys((*UNITS,*(unit(u) for u in UNITS))))
    USER_UNITS=tuple(dict.fromkeys((*USER_UNITS,*(unit(u) for u in USER_UNITS),'pi-control-audio.service')))
JOURNAL_PATTERN = (r'(?i)USB disconnect|new .*USB device|New USB device found|reset .*USB device|usb .*error -'
                   r'|I/O error|device offline error|blk_update_request|ntfs|FAT-fs|EXT4-fs|exfat'
                   r'|under.?voltage|voltage normal|throttl|over.?temperature|Out of memory|oom-kill|Killed process'
                   r'|device \(wlan0\)|Traceback|failed|exception|error|timed out|Main process exited|Scheduled restart')


def clean(value, limit=800):
    text = value if isinstance(value, str) else ''
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
    text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
    # Selected messages only; redact common credential forms before persistence.
    text = re.sub(r'(?i)\b(bearer)\s+\S+', r'\1 [ẩn]', text)
    text = re.sub(r'''(?ix)(\b(?:password|passwd|token|secret|api[_-]?key|access[_-]?code|authkey|authorization)\b["']?\s*[=:]\s*).*''', r'\1[ẩn]', text)
    text = re.sub(r'https?://\S+', '[URL ẩn]', text)
    return text[:limit]


def journal_summary(kind, title, raw, source):
    """Group a failure episode, retaining its device/service and error family."""
    family = ''
    if source == 'cloudflared.service':
        if 'Incoming request ended abruptly: context canceled' in raw:
            return None  # Normal browser/stream cancellation, not a tunnel outage.
        if re.search(r'lookup .*?(?:timeout|no such host|server misbehaving)', raw, re.I):
            title, family = 'Tunnel không phân giải được DNS', 'dns'
        elif 'Unable to reach the origin service' in raw:
            title, family = 'Tunnel chưa kết nối được Dashboard', 'origin'
        elif re.search(r'no recent network activity|context deadline exceeded|failed to dial to edge with quic|handshake did not complete', raw, re.I):
            title, family = 'Tunnel mất kết nối máy chủ', 'connection'
        elif 'unexpected EOF' in raw:
            title, family = 'Luồng qua Tunnel bị ngắt', 'stream-eof'
    if kind in ('service', 'camera') and not family:
        match = re.search(r'error="([^"]+)"', raw)
        reason = match[1] if match else raw
        reason = re.sub(r'^\d{4}-\d\d-\d\dT\S+\s+\w+\s+', '', reason)
        reason = re.sub(r'^\[[^\]]+\]\s*\[\d+\]\s*\[\w+\]\s*', '', reason)
        reason = re.sub(r'^\[\d+:\d+:[^:]+:', '[process:', reason)
        reason = re.sub(r'\b\d{8}T\d{6}-[a-f0-9]+\b|0x[a-f0-9]+|\b\d{4,}\b|\b[a-f0-9]{16,}\b', '[id]', reason, flags=re.I)
        family = hashlib.sha256(clean(reason).encode()).hexdigest()[:16]
    if kind == 'network':
        state = re.search(r'state change:\s*(\S+)\s*->\s*(\S+)', raw)
        if state: family = state[1]+'->'+state[2]
    device = re.search(r'\b(?:usb [\d.-]+|sd[a-z]+\d*|mmcblk\d+(?:p\d+)?)\b', raw) if kind in ('storage','usb') else None
    group = ':'.join((kind, title, device[0] if device else source, family))
    return title, group


def compact_events(items):
    """One-time repair of older snapshots; count and episode boundaries survive."""
    groups, result = {}, []
    for original in sorted(items, key=lambda r:r.get('first_timestamp',r['timestamp'])):
        row = dict(original)
        if row.get('origin') == 'journal':
            source = row.get('source') or row.get('group','').rsplit(':',1)[-1]
            summary = journal_summary(row.get('kind','system'),row['message'],row.get('detail',''),source)
            if summary is None: continue
            row['message'],row['group'] = summary
            row['source'] = source
        key = tuple(row.get(k,'') for k in ('kind','group','message','level','origin','boot'))
        previous = groups.get(key)
        first = row.get('first_timestamp',row['timestamp'])
        if previous and first <= previous['timestamp']+300:
            previous['count'] = min(1000000,previous.get('count',1)+row.get('count',1))
            previous['first_timestamp'] = min(previous.get('first_timestamp',previous['timestamp']),first)
            if row['timestamp'] >= previous['timestamp']:
                previous.update(timestamp=row['timestamp'],detail=row.get('detail',''))
        else:
            row.setdefault('first_timestamp',first)
            row.setdefault('count',1)
            result.append(row)
            groups[key] = row
    return sorted(result,key=lambda r:r['timestamp'])


def classify(entry):
    """No arbitrary application output: explicitly recognized messages only."""
    raw = entry.get('MESSAGE')
    if not isinstance(raw, str):
        return None
    kernel = entry.get('_TRANSPORT') == 'kernel'
    unit = entry.get('_SYSTEMD_UNIT', '')
    user_unit = entry.get('_SYSTEMD_USER_UNIT', '')
    kind = level = title = None
    if kernel:
        if re.search(r'I/O error|device offline error|Buffer I/O|blk_update_request', raw, re.I):
            kind, level, title = 'storage', 'error', 'Ổ lưu phát sinh lỗi đọc/ghi'
        elif re.search(r'(ntfs|FAT-fs|EXT4-fs|exfat).*?(dirty|error|failed|chkdsk|fsck|corrupt|not properly unmounted)', raw, re.I):
            kind, level, title = 'storage', 'error', 'Hệ thống tệp cần kiểm tra'
        elif re.search(r'usb [\d.-]+: USB disconnect', raw):
            kind, level, title = 'usb', 'warning', 'Thiết bị USB mất kết nối'
        elif re.search(r'usb [\d.-]+: (?:new .*USB device|New USB device found)', raw):
            kind, level, title = 'usb', 'info', 'Thiết bị USB được nhận'
        elif re.search(r'reset .*USB device|usb .*error -\d+', raw, re.I):
            kind, level, title = 'usb', 'warning', 'Kết nối USB bị đặt lại hoặc báo lỗi'
        elif re.search(r'under.?voltage|voltage normal|throttl|over.?temperature', raw, re.I):
            kind, level, title = 'health', 'warning', 'Nguồn hoặc nhiệt độ có thay đổi'
        elif re.search(r'Out of memory|oom-kill|Killed process \d+', raw, re.I):
            kind, level, title = 'health', 'error', 'Hệ thống thiếu bộ nhớ'
    elif unit == 'NetworkManager.service' and re.search(r'device \(wlan0\).*?(state change|Activation:|disconnected)', raw):
        kind, level, title = 'network', 'info', 'Wi-Fi thay đổi trạng thái'
    elif (unit in UNITS or user_unit in USER_UNITS) and re.search(r'Traceback|failed|exception|error|timed out', raw, re.I):
        kind, level, title = 'camera' if user_unit in ('pi-camera.service','pi-control-camera.service') else 'service', 'error', 'Dịch vụ ghi nhận lỗi'
    elif entry.get('_PID') == '1' and entry.get('_UID') == '0' and any(u in raw for u in (*UNITS, *USER_UNITS)) and re.search(r'Failed|Main process exited|Scheduled restart', raw):
        kind, level, title = 'service', 'warning', 'Dịch vụ dừng hoặc khởi động lại'
        unit=next(u for u in (*UNITS,*USER_UNITS) if u in raw)
    if not kind:
        return None
    try:
        timestamp = float(entry['__REALTIME_TIMESTAMP']) / 1000000
        if not 0 < timestamp < 1e12:
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    cursor = entry.get('__CURSOR', '')
    if not isinstance(cursor, str) or not cursor or len(cursor) > 1024:
        return None
    source = user_unit or unit
    summary = journal_summary(kind,title,raw,source)
    if summary is None: return None
    title,group = summary
    detail = clean(raw)
    return dict(id=hashlib.sha256(cursor.encode()).hexdigest()[:24], timestamp=timestamp,
                kind=kind, level=level, message=title, detail=detail, group=group,
                origin='journal', source=source, boot=clean(entry.get('_BOOT_ID', ''), 64))


def bounded_command(args, timeout=3, limit=2 * 1024 * 1024, empty_ok=False):
    """Read a fixed journal query without unbounded stdout or stderr buffers."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data, errors = bytearray(), bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, (data, limit))
            selector.register(process.stderr, selectors.EVENT_READ, (errors, 8192))
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('journal timeout')
                ready = selector.select(remaining)
                if not ready:
                    raise TimeoutError('journal timeout')
                for key, _ in ready:
                    buffer, maximum = key.data
                    chunk = os.read(key.fd, min(65536, maximum + 1 - len(buffer)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        buffer.extend(chunk)
                        if len(buffer) > maximum:
                            raise ValueError('journal response limit')
        status = process.wait(timeout=max(.1, deadline-time.monotonic()))
        # journalctl --grep returns 1 for no matches. Real failures have stderr.
        if status and not (empty_ok and status == 1 and not data.strip() and not errors.strip()):
            raise OSError('journal unavailable')
        return data.decode('utf-8', errors='replace')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


class EventStore:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.lock = threading.RLock()
        self.items, self.cursor, self.boot = [], '', ''
        self.cursor_at = 0
        self.seen = deque(maxlen=4096)
        self.dirty = False
        self.last_flush = self.clock()
        self.retry_at = 0
        self.error = ''
        self.last_read = 0
        self.read_error = ''
        self.limited = False
        self.started = int(self.clock())
        try:
            if self.path.is_symlink() or self.path.stat().st_size > MAX_BYTES:
                raise ValueError('unsafe event snapshot')
            saved = json.loads(self.path.read_text())
            if saved.get('version') != 1 or not isinstance(saved.get('items'), list):
                raise ValueError('invalid event snapshot')
            self.items = [r for r in saved['items'][-LIMIT:] if self.valid_row(r)]
            if saved.get('grouping') != GROUPING_VERSION:
                self.items = compact_events(self.items)
                self.dirty = True
            self.cursor = saved.get('cursor', '') if isinstance(saved.get('cursor'), str) else ''
            cursor_at=saved.get('cursor_at',0)
            self.cursor_at=cursor_at if isinstance(cursor_at,(int,float)) and 0 <= cursor_at < 1e18 else 0
            self.boot = saved.get('boot', '') if isinstance(saved.get('boot'), str) else ''
            self.seen.extend(s for s in saved.get('seen', [])[-4096:] if isinstance(s, str) and len(s)<=64)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            self.error = 'Không đọc được tệp nhật ký cũ; tệp được giữ nguyên đến lần lưu thành công'

    @staticmethod
    def valid_row(row):
        return (isinstance(row, dict) and isinstance(row.get('timestamp'), (int,float))
                and 0 < row['timestamp'] < 1e12 and isinstance(row.get('message'), str)
                and isinstance(row.get('id'), str) and len(row['id'])<=64)

    def add(self, kind, message, level='info', detail='', *, ident=None, timestamp=None, group=None, origin='observed', boot='', source=''):
        timestamp = self.clock() if timestamp is None else timestamp
        if not 0 < timestamp <= self.clock()+300 or timestamp < self.clock()-RETENTION:
            return
        message, detail = clean(message,180), clean(detail)
        ident = ident or hashlib.sha256(f'{time.monotonic_ns()}:{kind}:{message}'.encode()).hexdigest()[:24]
        group = group or f'{kind}:{message}'
        with self.lock:
            if ident in self.seen:
                return
            self.seen.append(ident)
            match = next((r for r in reversed(self.items) if r.get('group')==group
                          and r.get('message')==message
                          and r.get('level')==level and r.get('origin')==origin
                          and r.get('boot','')==boot
                          and r.get('first_timestamp',r['timestamp'])-300 <= timestamp <= r['timestamp']+300), None)
            if match:
                match['first_timestamp'] = min(match.get('first_timestamp',match['timestamp']),timestamp)
                match['count'] = min(1000000,match.get('count',1)+1)
                if timestamp >= match['timestamp']: match.update(timestamp=timestamp,detail=detail)
            else:
                self.items.append(dict(id=ident,timestamp=timestamp,first_timestamp=timestamp,kind=kind,
                                       level=level,message=message,detail=detail,count=1,group=group,origin=origin,boot=boot,source=source))
            self.items = sorted((r for r in self.items if r['timestamp'] >= self.clock()-RETENTION),
                                key=lambda r:r['timestamp'])[-LIMIT:]
            self.dirty = True

    def ingest(self, entries):
        # --grep with -n makes journalctl return newest first. Always consume in
        # timestamp order and save the newest cursor, including ignored messages.
        def timestamp(entry):
            try: value=float(entry.get('__REALTIME_TIMESTAMP',0))
            except (TypeError,ValueError,OverflowError): return 0
            return value if 0 < value < 1e18 else 0
        for entry in sorted((r for r in entries if isinstance(r,dict)),key=timestamp):
            row = classify(entry)
            if row:
                self.add(row['kind'],row['message'],row['level'],row['detail'],ident=row['id'],
                         timestamp=row['timestamp'],group=row['group'],origin='journal',boot=row['boot'],source=row['source'])
            cursor = entry.get('__CURSOR')
            if isinstance(cursor,str) and len(cursor)<=1024 and timestamp(entry) >= self.cursor_at:
                self.cursor = cursor
                self.cursor_at = timestamp(entry)
        self.last_read = int(self.clock())
        self.read_error = ''

    def prune(self):
        with self.lock:
            kept=[r for r in self.items if r['timestamp']>=self.clock()-RETENTION]
            if len(kept)!=len(self.items):
                self.items=kept;self.dirty=True

    def snapshot(self):
        with self.lock:
            rows = [dict(r) for r in reversed(self.items) if r['timestamp'] >= self.clock()-RETENTION][:400]
            return dict(events=rows, meta=dict(available=True, retention_days=30, stored=len(self.items),
                        maximum=LIMIT, shown=len(rows), last_read=self.last_read, started=self.started,
                        limited=self.limited, error=self.error or self.read_error, pending=self.dirty,
                        checkpoint_seconds=60, scope='Nhật ký chọn lọc; không bảo đảm đầy đủ mọi log Linux'))

    def flush(self, force=False):
        with self.lock:
            now = self.clock()
            if not self.dirty or now < self.retry_at or not force and now-self.last_flush < 60:
                return False
            temporary = self.path.with_suffix('.tmp')
            try:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if self.path.is_symlink() or temporary.is_symlink():
                    raise ValueError('unsafe snapshot path')
                payload = dict(version=1,grouping=GROUPING_VERSION,items=self.items,cursor=self.cursor,cursor_at=self.cursor_at,boot=self.boot,seen=list(self.seen))
                data = json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
                if len(data)>MAX_BYTES:
                    raise ValueError('snapshot too large')
                with temporary.open('wb') as handle:
                    os.chmod(temporary,0o600)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary,self.path)
                directory=os.open(self.path.parent,os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
                self.dirty=False;self.last_flush=now;self.error='';self.retry_at=0
                return True
            except (OSError, ValueError):
                self.error='Chưa lưu được nhật ký; bản mới còn trong RAM'
                self.retry_at=now+60
                return False


def camera_status():
    # Read-only IPC; never registers a viewer or starts/stops capture.
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(.5)
        # The observer binds the runtime directory outside ProtectHome's hidden tree.
        runtime = os.environ.get('PIWIFI_CAMERA_RUNTIME', str(desktop_runtime()))
        connection.connect(str(Path(runtime) / 'pi-camera.sock'))
        connection.sendall(b'{"action":"status"}\n')
        raw=connection.makefile('rb').readline(65537)
        if len(raw)>65536: raise ValueError('camera reply too large')
        reply=json.loads(raw)
        if not reply.get('ok') or not isinstance(reply.get('data'),dict): raise ValueError('camera unavailable')
        return reply['data']


def mounted_volumes():
    result={}
    # ProtectSystem makes mounts read-only inside the observer's own namespace.
    # PID 1 describes the host mounts, rather than those sandbox restrictions.
    for line in Path('/proc/1/mountinfo').read_text().splitlines():
        left,right=line.split(' - ',1); fields=left.split(); fs,source,*_=right.split()
        target=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),fields[4])
        if target.startswith(('/mnt/','/media/')) and source.startswith('/dev/'):
            result[target]=dict(source=source,fs=fs,readonly='ro' in fields[5].split(','))
    return result


class SystemMonitor:
    def __init__(self,path):
        self.store=EventStore(path)
        self.stop_event=threading.Event()
        self.worker=None
        self.camera=None
        self.camera_failures=0
        self.mounts=None
        self.net=None
        self.flags={}
        self.access_checked=False

    def read_journal(self):
        if not self.access_checked:
            # journalctl may return success with empty output when access is denied.
            probe=bounded_command(['journalctl','--no-pager','--quiet','-b','0','-n','1','-o','json','_TRANSPORT=kernel'],limit=65536)
            if not any(line.startswith('{') for line in probe.splitlines()):
                raise OSError('kernel journal access unavailable')
            self.access_checked=True
        args=['journalctl','--no-pager','--quiet','-o','json','--output-fields=MESSAGE,__CURSOR,__REALTIME_TIMESTAMP,_BOOT_ID,_TRANSPORT,_SYSTEMD_UNIT,_SYSTEMD_USER_UNIT,_PID,_UID','-n','1000','--grep='+JOURNAL_PATTERN]
        if self.store.cursor:
            args+=['--after-cursor='+self.store.cursor]
        else:
            args+=['-b','0','--since=-24hours']
        matches=['_TRANSPORT=kernel','_PID=1']+[f'_SYSTEMD_UNIT={u}' for u in UNITS]+[f'_SYSTEMD_USER_UNIT={u}' for u in USER_UNITS]
        for i,match in enumerate(matches):
            if i: args.append('+')
            args.append(match)
        output=bounded_command(args, empty_ok=True)
        entries=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.store.limited=self.store.limited or len(entries)>=1000
        self.store.ingest(entries)

    def observe_camera(self, data):
        previous=self.camera
        current=dict(recording=bool(data.get('recording')),rendering=bool(data.get('rendering')),
                     session=(data.get('session') or {}).get('id'),render_session=(data.get('render_session') or {}).get('id'),
                     error=clean(data.get('error','')),last_result=data.get('last_result') or {},dropped=data.get('dropped_frames',0))
        result=current['last_result']
        if current['recording'] and (previous is None or current['session']!=previous['session']):
            self.store.add('camera','Đang ghi phiên camera','info',f"Phiên {current['session']} · đã quan sát lúc kết nối bộ giám sát" if previous is None else f"Phiên {current['session']}")
        if previous and previous['recording'] and not current['recording']:
            self.store.add('camera','Phiên camera đã dừng ghi','info',f"Phiên {previous['session']}" )
        if current['rendering'] and (not previous or not previous['rendering']):
            self.store.add('camera','Camera đang ghép video','info',f"Phiên {current['render_session'] or 'chưa xác định'}")
        if result.get('id') and previous and result.get('id')!=previous['last_result'].get('id'):
            ready=result.get('state')=='ready'
            self.store.add('camera','Ghép video hoàn tất' if ready else 'Phiên camera chưa có video hoàn tất',
                           'info' if ready else 'warning',f"Phiên {result['id']} · {result.get('frames',0)} ảnh · {clean(result.get('note',''))}")
        if current['error'] and (not previous or current['error']!=previous['error']):
            self.store.add('camera','Camera báo lỗi','error',current['error'])
        elif previous and previous['error'] and not current['error']:
            self.store.add('camera','Camera đã hết thông báo lỗi')
        if previous and current['dropped']>previous['dropped']:
            self.store.add('camera','Camera đã bỏ qua khung ảnh lỗi','warning',
                           f"Tăng {current['dropped']-previous['dropped']} khung · tổng {current['dropped']} từ lúc agent chạy; phiên ghi không nhất thiết bị dừng")
        self.camera=current

    def observe_mounts(self, current):
        previous=self.mounts
        if previous is not None:
            for target in previous.keys()-current.keys():
                self.store.add('storage','Phân vùng không còn được gắn','warning',target,group='mount:'+target)
        for target,value in current.items():
            old=previous.get(target) if previous is not None else None
            if old!=value and (previous is not None or value['readonly']):
                self.store.add('storage','Phân vùng đang chỉ đọc' if value['readonly'] else 'Phân vùng đã được gắn',
                               'warning' if value['readonly'] else 'info',f"{target} · {value['source']} · {value['fs']}",group='mount:'+target)
        self.mounts=current

    def observe_health(self, data, checks):
        flags=dict(temperature=data.get('temperature') is not None and data['temperature']>=80,
                   disk=any(d.get('percent',0)>=90 for d in data.get('disks',[])),
                   undervoltage=data.get('power',{}).get('undervoltage'),throttled=data.get('power',{}).get('throttled'))
        labels=dict(temperature='Nhiệt độ SoC cao',disk='Phân vùng sử dụng từ 90%',undervoltage='Nguồn điện đang yếu',throttled='Pi đang giảm hiệu năng')
        for service in data.get('services',[]):
            if service['state'] in ('active','inactive','failed'):
                key='service:'+service['name'];flags[key]=service['state']!='active';labels[key]='Dịch vụ '+service['name']+' không hoạt động'
        for key,value in flags.items():
            if value is not None and value!=self.flags.get(key,False):
                self.store.add('service' if key.startswith('service:') else 'health',labels[key] if value else labels[key]+' · đã hết cảnh báo','warning' if value else 'info',group=key)
        self.flags=flags
        layers={r['name']:r for r in checks.get('layers',[])}
        network={k:(layers[k].get('state'),clean(layers[k].get('detail',''))) for k in ('Wi-Fi','Địa chỉ IP','Internet','DNS') if k in layers}
        if self.net is not None and network and network!=self.net:
            for key,value in network.items():
                if value!=self.net.get(key):
                    self.store.add('network',key+' thay đổi','info' if value[0] in ('ok','na') else 'warning',value[1])
        if network:self.net=network

    def tick(self):
        try:
            self.read_journal()
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
            self.store.read_error='Chưa đọc được log Linux; chỉ có các trạng thái quan sát được'
            # Invalid/expired cursors recover with a bounded current-boot read.
            self.store.cursor=''
        try:self.observe_mounts(mounted_volumes())
        except (OSError,ValueError):pass
        try:
            self.observe_camera(camera_status())
            if self.camera_failures>=3:self.store.add('camera','Đã kết nối lại bộ giám sát camera')
            self.camera_failures=0
        except (OSError,ValueError,KeyError,TypeError):
            self.camera_failures+=1
            if self.camera_failures==3:self.store.add('camera','Chưa đọc được trạng thái camera','warning','Không suy ra camera đã dừng hoặc mất ảnh')
        self.store.prune()
        self.store.flush()

    def start(self):
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if self.store.boot!=boot:self.store.cursor='';self.store.cursor_at=0
        self.store.boot=boot
        btime=next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
        self.store.add('system','Pi khởi động','info','Thời điểm khởi động do kernel báo; không xác định nguyên nhân lần tắt trước',ident=hashlib.sha256(boot.encode()).hexdigest()[:24],timestamp=btime,boot=boot)
        def run():
            while not self.stop_event.is_set():
                try:self.tick()
                except Exception:self.store.read_error='Bộ thu nhật ký cần kiểm tra; dữ liệu cũ vẫn được giữ'
                self.stop_event.wait(10)
        self.worker=threading.Thread(target=run,daemon=True)
        self.worker.start()

    def close(self):
        self.stop_event.set()
        if self.worker:self.worker.join(timeout=5)
        self.store.flush(force=True)
