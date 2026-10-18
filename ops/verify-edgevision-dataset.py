"""Verify live dataset reads without creating/approving any production samples."""
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

root=Path.home()/'edgevision-camera/data/dataset'
def inventory():
    return {str(path): (path.stat().st_size,path.stat().st_mtime_ns)
            for path in root.rglob('*') if path.is_file()}
def read(path):
    with urlopen('http://127.0.0.1:18766'+path,timeout=8) as response:return response.read()
matches=[]
for entry in Path('/proc').glob('[0-9]*'):
    try:
        command=(entry/'cmdline').read_bytes()
        if b'edgevision-camera/venv/bin/python' in command and b'\x00-m\x00edgevision\x00' in command:
            matches.append(entry.name)
    except OSError:
        continue
assert len(matches)==1,'Expected one camera application process'
pid=matches[0]
def writes():
    counters=dict(line.split(':',1) for line in Path(f'/proc/{pid}/io').read_text().splitlines())
    return int(counters['write_bytes'])
before,write_before=inventory(),writes()
for _ in range(10):
    dataset=json.loads(read('/api/dataset'))
    for row in dataset['items']:
        raw=read('/api/dataset/image?id='+row['id'])
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
assert inventory()==before,'Read requests modified dataset files'
assert writes()==write_before,'Read requests caused application write_bytes'
assert dataset['items'] and all(not row['reviewed'] and row['domain']=='trial' for row in dataset['items'])
for suffix in ('','?include_trial=1'):
    try:read('/api/dataset/export'+suffix)
    except HTTPError as error:assert error.code==400
    else:raise AssertionError('Unreviewed images must not export')
print(json.dumps({'read_rounds':10,'images':len(dataset['items']),
                  'reviewed':sum(row['reviewed'] for row in dataset['items']),
                  'draft_boxes':[len(row['labels']) for row in dataset['items']],
                  'image_bytes':dataset['image_bytes'],
                  'file_changes':0,'application_write_bytes_delta':writes()-write_before}))
