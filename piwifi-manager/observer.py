"""Local history and explicit, bounded network diagnostics."""
import json
import os
import socket
import sqlite3
import subprocess
import time
from pathlib import Path
from contextlib import contextmanager
from metrics import collect, fresh
from state import read
from collections import deque
import threading
import socketserver
from security import status as security_status
from storage_writes import WriteTracker, system_sample

SAMPLES = deque(maxlen=10080)
HEALTH_EVENTS = deque(maxlen=500)
RAM_LOCK = threading.Lock()
IPC = Path('/run/piwifi-observer/history.sock')
WRITE_TRACKER = None
WRITE_ERROR = ''

def bucket_history(rows):
    size = max(1, (len(rows)+359)//360)
    result = []
    for index in range(0,len(rows),size):
        bucket=rows[index:index+size]
        point={'timestamp':bucket[-1]['timestamp']}
        for key in ('cpu','temperature','ram','rx','tx'):
            values=[p[key] for p in bucket if p.get(key) is not None]
            point[key]=max(values) if values else None
        result.append(point)
    return result

def ram_query(kind,hours=24,days=30):
    if kind=='storage-writes':
        if WRITE_TRACKER:
            try:result=WRITE_TRACKER.query(hours,days)
            except sqlite3.Error:return dict(available=False,error='Không đọc được lịch sử ghi; cơ sở dữ liệu được giữ nguyên')
            if WRITE_ERROR:result['error']=WRITE_ERROR
            result['stale']=time.time()-result.get('timestamp',0)>45
            return result
        return dict(available=False,error=WRITE_ERROR or 'Thống kê ghi chưa sẵn sàng')
    with RAM_LOCK:
        if kind=='events': return list(HEALTH_EVENTS)
        if kind!='history' or hours not in (1,24,168): raise ValueError('Invalid query')
        return bucket_history([p for p in SAMPLES if p['timestamp']>=time.time()-hours*3600])

def ipc_read(kind,hours=24,days=30):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(IPC))
            connection.sendall(json.dumps({'kind':kind,'hours':hours,'days':days}).encode()+b'\n')
            stream=connection.makefile('rb')
            raw=stream.readline(1048576)
            return json.loads(raw)
    except (OSError,ValueError,AttributeError): return []

class RamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(2)
        try:
            request=json.loads(self.rfile.readline(1024))
            response=ram_query(request.get('kind'),request.get('hours',24),request.get('days',30))
            self.wfile.write(json.dumps(response).encode()+b'\n')
        except (OSError,ValueError,TypeError): pass

class RamServer(getattr(socketserver, 'UnixStreamServer', socketserver.TCPServer)):
    allow_reuse_address=True


DB = Path(os.environ.get('PIWIFI_HISTORY_DB', '/var/lib/piwifi-observer/history.db'))
SNAPSHOT = Path('/run/piwifi-observer/metrics.json')

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=5)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA wal_autocheckpoint=256')
    db.execute('CREATE TABLE IF NOT EXISTS samples (timestamp INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp INTEGER, message TEXT, level TEXT)')
    try:
        with db:
            yield db
    finally:
        db.close()

@contextmanager
def reader():
    # Readers must not run schema setup or change journal mode.
    db = sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        yield db
    finally:
        db.close()

def history(hours=24):
    return ipc_read('history',hours)

def events():
    result=read('events.json',[]) + ipc_read('events')
    return sorted(result,key=lambda e:e['timestamp'],reverse=True)[:200]

def current():
    try:
        data = json.loads(SNAPSHOT.read_text())
        data['stale'] = time.time() - data['timestamp'] > 45
        data['server_time'] = int(time.time())
        return fresh(data)
    except (OSError, ValueError):
        return dict(collect(), stale=True, server_time=int(time.time()))

def diagnostics(status):
    """Fixed destinations only; cached periodically, never arbitrary user URLs."""
    layers = []
    def add(name, state, detail):
        layers.append(dict(name=name, state=state, detail=detail))
    ap = status.get('active') == 'Pi-Fallback'
    add('Wi-Fi', 'ok' if status.get('active') else 'failed', status.get('active') or 'Chưa có kết nối')
    add('Địa chỉ IP', 'ok' if status.get('ip') else 'failed', status.get('ip') or 'Chưa nhận IP')
    gateway = status.get('gateway')
    if ap:
        add('Gateway', 'na', 'Hotspot quản trị cục bộ')
        add('DNS', 'na', 'Không yêu cầu Internet trong chế độ hotspot')
        add('Internet', 'na', 'Không yêu cầu Internet trong chế độ hotspot')
    else:
        reachable = False
        if gateway:
            try:
                import ipaddress
                ipaddress.ip_address(gateway)
                p = subprocess.run(['/usr/bin/ping', '-I', 'wlan0', '-c', '1', '-W', '2', gateway],
                                   capture_output=True, timeout=4)
                reachable = p.returncode == 0
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass
        add('Gateway', 'ok' if reachable else 'unknown', gateway or 'Chưa có gateway; ping thất bại không kết luận router hỏng')
        dns_ok = False
        try:
            p = subprocess.run(['/usr/bin/getent', 'ahostsv4', 'www.raspberrypi.com'], capture_output=True, timeout=4)
            dns_ok = p.returncode == 0 and bool(p.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass
        add('DNS', 'ok' if dns_ok else 'failed', 'Phân giải www.raspberrypi.com qua DNS hệ thống')
        internet = False
        try:
            with socket.create_connection(('1.1.1.1', 443), timeout=3):
                internet = True
        except OSError:
            pass
        add('Internet', 'ok' if internet else 'unknown', 'TCP 1.1.1.1:443; một đích thử không chứng minh toàn bộ Internet')
    try:
        with socket.create_connection(('127.0.0.1', 18765), timeout=2):
            web_ok = True
    except OSError:
        web_ok = False
    add('Dashboard', 'ok' if web_ok else 'failed', 'Cổng ứng dụng 18765 trên Pi')
    return dict(timestamp=int(time.time()), layers=layers, scope='DNS và Internet theo tuyến mặc định của hệ thống')

def _run():
    global WRITE_ERROR
    previous = {}
    last_save = last_diagnose = 0
    checks = {}
    while True:
        started = time.monotonic()
        if WRITE_TRACKER:
            try:
                WRITE_TRACKER.sample(system_sample())
                WRITE_TRACKER.checkpoint()
                WRITE_ERROR=''
            except Exception:
                WRITE_ERROR='Chưa cập nhật/lưu được thống kê ghi SD; dữ liệu có thể đã cũ'
        try:
            data = collect()
            now = data['timestamp']
            if now - last_diagnose >= 60:
                try:
                    # Diagnostics only need connection/IP/gateway, not every saved profile.
                    p = subprocess.run(['/usr/bin/nmcli','-g','GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY','device','show','wlan0'],capture_output=True,text=True,timeout=2)
                    if p.returncode: raise RuntimeError('Không đọc được trạng thái mạng')
                    fields=p.stdout.splitlines()
                    if len(fields)<3:raise RuntimeError('Chưa đủ thông tin mạng')
                    checks=diagnostics(dict(active=fields[0],ip=fields[1],gateway=fields[-1]))
                except Exception:
                    checks = dict(timestamp=now, layers=[], error='Chưa chẩn đoán được mạng')
                last_diagnose = now
            data['diagnostics'] = checks
            data['ssh_security'] = security_status()
            temporary = SNAPSHOT.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            temporary.replace(SNAPSHOT)
            if now - last_save >= 60:
                net = next((n for n in data['network'] if n['name'] == 'wlan0'), {})
                sample = dict(cpu=data['cpu'], temperature=data['temperature'], ram=data['ram']['percent'],
                              rx=net.get('rx_rate'), tx=net.get('tx_rate'))
                flags = dict(temperature=data['temperature'] is not None and data['temperature'] >= 80,
                             disk=any(d['percent'] >= 90 for d in data['disks']),
                             undervoltage=data['power'].get('undervoltage'), throttled=data['power'].get('throttled'))
                labels = dict(temperature='Nhiệt độ SoC cao', disk='Phân vùng sử dụng từ 90%',
                              undervoltage='Nguồn điện đang yếu', throttled='Pi đang giảm hiệu năng')
                for service in data['services']:
                    if service['state'] in ('active', 'inactive', 'failed'):
                        key = 'service:' + service['name']
                        flags[key] = service['state'] != 'active'
                        labels[key] = 'Dịch vụ ' + service['name'] + ' không hoạt động'
                with RAM_LOCK:
                    SAMPLES.append(dict(timestamp=now,**sample))
                    for flag,value in flags.items():
                        if value is not None and value!=previous.get(flag,False):
                            HEALTH_EVENTS.append(dict(timestamp=now,message=labels[flag] if value else labels[flag]+' · đã hết cảnh báo',level='warning' if value else 'info',kind='health'))
                previous=flags
                last_save=now
        except Exception as exc:
            # Collection failures must not generate repeating journal writes.
            pass
        time.sleep(max(1, 10 - (time.monotonic() - started)))

def run():
    global WRITE_TRACKER,WRITE_ERROR
    import signal
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    # /run must be tmpfs; never silently fall back to SD for snapshots/socket.
    mounts=Path('/proc/mounts').read_text().splitlines()
    if not any(line.split()[1:3]==['/run','tmpfs'] for line in mounts):
        raise RuntimeError('/run is not tmpfs')
    IPC.parent.mkdir(parents=True,exist_ok=True)
    IPC.unlink(missing_ok=True)
    try:
        WRITE_TRACKER=WriteTracker('/var/lib/piwifi-observer/storage-writes.db')
    except Exception:
        WRITE_ERROR='Không mở được cơ sở dữ liệu lượng ghi; dữ liệu cũ được giữ nguyên'
    with RamServer(str(IPC),RamHandler) as server:
        os.chmod(IPC,0o600)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try: _run()
        except KeyboardInterrupt: pass
        finally:
            server.shutdown()
            if WRITE_TRACKER:
                try:
                    WRITE_TRACKER.sample(system_sample())
                    WRITE_TRACKER.close()
                except Exception:pass
            IPC.unlink(missing_ok=True)

if __name__=='__main__': run()
