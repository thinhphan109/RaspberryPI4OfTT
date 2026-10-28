#!/usr/bin/env python3
"""Bounded read-only HTTP audit on the Pi; never outputs credentials or cookies.

Uses the running Dashboard's same-user environment to create a local audit
session. Does not start cameras, scan Wi-Fi, pair devices or modify playback.
"""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

from flask import Flask
from flask.sessions import SecureCookieSessionInterface

BASE = 'http://127.0.0.1:18765'
PATHS = ('/login', '/', '/api/metrics', '/api/status', '/api/hub',
         '/api/events?summary=1', '/api/history?hours=24',
         '/api/storage-writes', '/api/deployments', '/api/audio',
         '/api/media', '/api/camera', '/api/gpio/status', '/api/security')


def credential():
    pid = subprocess.check_output(['systemctl', 'show',
        'pi-control-dashboard.service', '-p', 'MainPID', '--value'], text=True).strip()
    env = dict(part.split(b'=', 1) for part in Path('/proc', pid, 'environ').read_bytes().split(b'\0') if b'=' in part)
    app = Flask(__name__)
    app.secret_key = env[b'PIWIFI_SECRET'].decode()
    return SecureCookieSessionInterface().get_signing_serializer(app).dumps(
        {'logged_in': True, 'csrf': 'local-read-only-audit'})


def fetch(path, cookie=None, method='GET', payload=None):
    start = time.monotonic()
    headers = {'Cookie': 'session='+cookie} if cookie else {}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(BASE+path, headers=headers, method=method, data=payload)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=15) as response:
            raw = response.read(2*1024*1024)
            status = response.status
            redirected = response.url != BASE+path
    except urllib.error.HTTPError as exc:
        raw = exc.read(4096)
        status, redirected = exc.code, False
    except (OSError, TimeoutError):
        return {'path': path, 'status': 'timeout/connection-error', 'ms': round((time.monotonic()-start)*1000, 2)}, None
    result = {'path': path, 'status': status, 'ms': round((time.monotonic()-start)*1000, 2),
              'bytes': len(raw), 'redirected': redirected}
    try:
        data = json.loads(raw)
        result['ok'] = data.get('ok')
        return result, data.get('data')
    except (ValueError, AttributeError):
        return result, raw


def audit():
    cookie = credential()
    report = {'at': datetime.now(timezone.utc).isoformat(), 'routes': [], 'features': {}}
    data_by_path = {}
    for path in PATHS:
        samples = []
        for _ in range(3):
            result, data = fetch(path, cookie)
            samples.append(result)
            data_by_path[path] = data
        report['routes'].append({'path': path, 'samples': samples})
    for path in ('/api/audio', '/api/media', '/api/camera', '/api/metrics'):
        data = data_by_path.get(path)
        if not isinstance(data, dict):
            continue
        keys = {'/api/audio': ('errors', 'job', 'defaults'),
                '/api/media': ('available', 'provider', 'standby', 'playing', 'paused', 'nonstop'),
                '/api/camera': ('available', 'recording', 'rendering', 'frames', 'error', 'storage'),
                '/api/metrics': ('stale', 'timestamp', 'temperature', 'cpu', 'ram', 'power', 'disks')}[path]
        report['features'][path] = {key: data[key] for key in keys if key in data}
        if path == '/api/audio':
            bt = data.get('bluetooth', {})
            report['features'][path]['bluetooth'] = {key: bt.get(key) for key in ('available', 'powered', 'error')}
            report['features'][path]['audio_nodes'] = len(data.get('devices', []))
    fanout = ('/api/audio', '/api/media', '/api/metrics', '/api/events?summary=1',
              '/api/camera', '/api/deployments')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        report['parallel'] = [result for result, _ in pool.map(lambda path: fetch(path, cookie), fanout)]
    # Keep one incomplete HTTP client for <1s: a sync worker queues the normal
    # request; gthread accepts it immediately. Never wait for Gunicorn's timeout.
    with socket.create_connection(('127.0.0.1', 18765), timeout=2) as slow:
        slow.sendall(b'GET /login HTTP/1.1\r\nHost: localhost\r\n')
        time.sleep(0.1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(fetch, '/api/metrics', cookie)
            time.sleep(0.8)
            slow.shutdown(socket.SHUT_RDWR)
            report['incomplete_client_probe'] = pending.result()[0]
    for path in ('/api/audio', '/api/media', '/api/camera'):
        report.setdefault('csrf_checks', []).append(fetch(path, cookie, 'POST', b'{"action":"status"}')[0])
    report['unauthenticated'] = fetch('/api/metrics')[0]
    metadata = json.loads(Path('/var/lib/pi-control/control/modules.json').read_text())
    report['modules'] = {}
    manifests = [json.loads(path.read_text()) for path in (
        Path('/opt/pi-control-bootstrap-r3/manifest.json'),
        Path('/opt/pi-control-bootstrap-20261028-r4/manifest.json')) if path.exists()]
    for name, entry in metadata.items():
        manifest = next((value for value in manifests
            if value['modules'].get(name, {}).get('release') == entry['release']), None)
        if manifest is None:
            report['modules'][name] = {'release': entry['release'], 'verified': False, 'reason': 'No reviewed bundle found'}
            continue
        current = Path('/opt/pi-control', name, 'current')
        mismatches = []
        for file, expected in manifest['files'].items():
            prefix = 'files/'+name+'/'
            if not file.startswith(prefix):
                continue
            candidate = current / file.removeprefix(prefix)
            if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
                mismatches.append(file.removeprefix(prefix))
        report['modules'][name] = {'release': entry['release'], 'current': str(current.resolve()),
            'verified': not mismatches, 'bundle_mismatches': mismatches}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    audit()
