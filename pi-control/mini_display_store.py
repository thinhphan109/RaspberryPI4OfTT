"""Local clip queue and display selection shared by Dashboard and its worker."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile


DATA = Path('/srv/pi-control')
STORE = DATA / 'MiniDisplay'
RUNTIME = Path('/run/pi-control-display')
MAX_UPLOAD = 16 * 1024 * 1024
FORMATS = {'.gif': 'gif', '.mp4': 'mov', '.mov': 'mov', '.webm': 'matroska'}


def ready():
    return DATA.is_mount() and STORE.is_dir() and RUNTIME.is_dir()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def replace(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_json(path, value):
    replace(path, json.dumps(value, ensure_ascii=False).encode())


@contextmanager
def lock():
    import fcntl

    with (STORE / 'queue.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def enqueue(stream, filename, size):
    name = Path(filename.replace('\\', '/')).name[:140]
    kind = FORMATS.get(Path(name).suffix.lower())
    if kind is None or not 0 < size <= MAX_UPLOAD:
        raise ValueError('Chọn GIF, MP4, MOV hoặc WebM có dung lượng tối đa 16 MiB.')
    with lock():
        if (STORE / 'pending.json').exists():
            raise BlockingIOError('Đang xử lý một tệp. Đợi hoàn tất rồi thử lại.')
        with tempfile.NamedTemporaryFile(dir=STORE, delete=False) as uploaded:
            temporary = Path(uploaded.name)
            try:
                shutil.copyfileobj(stream, uploaded, 65536)
                if uploaded.tell() != size:
                    raise ValueError('Tệp tải lên chưa đầy đủ.')
                uploaded.close()
                temporary.replace(STORE / 'source')
                write_json(STORE / 'pending.json', {'name': name, 'format': kind})
            finally:
                temporary.unlink(missing_ok=True)


def status():
    available = ready()
    if not available:
        return {'ready': False, 'source': 'summary'}
    pending = read_json(STORE / 'pending.json')
    receipt = read_json(STORE / 'receipt.json')
    display = read_json(RUNTIME / 'status.json')
    return {
        'ready': bool(display),
        'frame': display.get('frame'),
        'active': display.get('active'),
        'scene': display.get('scene'),
        'connection': display.get('connection'),
        'busy': bool(pending),
        'clip': receipt.get('clip') if (STORE / 'clip.mp4').is_file() else None,
        'error': receipt.get('error'),
        'source': read_json(STORE / 'selection.json').get('source', 'summary'),
    }


def select(source):
    with lock():
        if source not in ('summary', 'clip'):
            raise ValueError('Nguồn hiển thị không hợp lệ.')
        if source == 'clip' and not (STORE / 'clip.mp4').is_file():
            raise ValueError('Cần tải và xử lý xong một tệp trước.')
        write_json(STORE / 'selection.json', {'source': source})
