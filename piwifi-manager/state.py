"""Bounded, root-owned operation state and event history (no credentials)."""
import fcntl
import json
import time
from pathlib import Path

ROOT = Path('/var/lib/piwifi-events')

def read(name, default=None):
    try:
        return json.loads((ROOT / name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def write(name, value):
    ROOT.mkdir(mode=0o755, exist_ok=True)
    target = ROOT / name
    temporary = ROOT / (name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.chmod(0o644)
    temporary.replace(target)

def event(kind, message, level='info'):
    ROOT.mkdir(mode=0o755, exist_ok=True)
    with (ROOT / 'events.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = read('events.json', [])
        entries.append(dict(timestamp=int(time.time()), kind=kind, message=message, level=level))
        write('events.json', entries[-500:])

def operation_update(operation, stage, **fields):
    current = read('operation.json', {})
    if current.get('id') != operation:
        raise RuntimeError('Thao tác đã được thay thế')
    current.update(stage=stage, updated=int(time.time()), **fields)
    steps = current.setdefault('steps', [])
    if not steps or steps[-1]['stage'] != stage:
        steps.append(dict(stage=stage, timestamp=current['updated']))
    current['steps'] = steps[-20:]
    write('operation.json', current)
    return current
