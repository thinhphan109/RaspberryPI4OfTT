"""Read-only app catalog and short-lived, per-session DNS diagnostics. No disk polling."""
import ipaddress
import base64
import datetime
import json
import os
import secrets
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

CATALOG = Path(__file__).with_name('apps.json')
from runtime_config import location
PASSWORD = location('adguard_credentials','/home/thinh/.config/adguardhome/credentials.json')
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))

def lan_ip(network):
    try:
        address = ipaddress.ip_interface(network.get('ip', '')).ip
        return str(address) if address.version == 4 and address.is_private else None
    except ValueError:
        return None

def applications(network):
    ip = lan_ip(network)
    result = []
    for item in catalog():
        row = dict(item)
        command = ['systemctl'] + (['--user'] if item.get('user_service') else [])
        try:
            env = dict(os.environ)
            if item.get('user_service'):
                env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}', DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
            state = subprocess.run(command + ['is-active', item['service']], capture_output=True, text=True, timeout=2, env=env).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            state = 'unknown'
        row.update(state=state or 'unknown', lan_url=f"http://{ip}:{item['port']}{item['path']}" if ip and not item.get('loopback') else None)
        result.append(row)
    return dict(ip=ip, ssid=network.get('active_ssid') or network.get('active'), apps=result,
                hostname='raspberrypi.local', updated=int(time.time()),
                hint='DNS chỉ dùng khi cùng mạng và Pi còn trực tuyến. YouTube không phải phép thử chặn DNS.')

def dns_probe(domain='doubleclick.net'):
    """Fixed local DNS A probe, including DNS header/answer validation."""
    ident = secrets.randbelow(65536)
    labels = b''.join(bytes([len(x)]) + x.encode('ascii') for x in domain.split('.')) + b'\0'
    packet = struct.pack('!6H', ident, 0x100, 1, 0, 0, 0) + labels + struct.pack('!2H', 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.connect(('127.0.0.1', 53))
        sock.send(packet)
        reply = sock.recv(4096)
    rid, flags, qd, an, _, _ = struct.unpack('!6H', reply[:12])
    if rid != ident or not flags & 0x8000 or flags & 15 or not an:
        return False
    # Skip names safely, accepting compression pointers in DNS replies.
    def skip(offset):
        for _ in range(128):
            length = reply[offset]
            if length & 0xC0 == 0xC0: return offset + 2
            offset += 1
            if not length: return offset
            offset += length
        raise ValueError('Invalid DNS name')
    offset = 12
    for _ in range(qd): offset = skip(offset) + 4
    for _ in range(an):
        offset = skip(offset)
        kind, cls, ttl, size = struct.unpack('!HHIH', reply[offset:offset+10])
        offset += 10
        if kind == 1 and cls == 1 and size == 4 and reply[offset:offset+4] == b'\0'*4: return True
        offset += size
    return False

def query_seen(domain, since):
    """Expose only the random challenge, never browsing history or API credentials."""
    credential = json.loads(PASSWORD.read_text())
    auth = base64.b64encode((credential['username']+':'+credential['password']).encode()).decode()
    url = 'http://127.0.0.1:18853/control/querylog?' + urllib.parse.urlencode({'search':domain, 'limit':20})
    with HTTP.open(urllib.request.Request(url, headers={'Authorization':'Basic '+auth}), timeout=3) as response:
        rows = json.load(response).get('data', [])
    for row in rows:
        if row.get('question', {}).get('name', '').rstrip('.') != domain: continue
        stamp=datetime.datetime.fromisoformat(row['time'].replace('Z','+00:00')).timestamp()
        if stamp >= since-2:return True
    return False
