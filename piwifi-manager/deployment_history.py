"""Action-only deploy ledger, with idempotent import of historical SD records."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

MAX_BYTES=8*1024*1024
MAX_EVENTS=10000


def bounded_bytes(path,limit):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('Unsafe history file')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('History file too large')
    return raw


def checked_json(path,limit=MAX_BYTES):
    return json.loads(bounded_bytes(path,limit))


def validate_import(path):
    raw=bounded_bytes(path,MAX_BYTES)
    checksum=path.with_suffix(path.suffix+'.sha256')
    if checksum.is_symlink() or not checksum.is_file() or checksum.stat().st_size>1024:raise ValueError('Missing history checksum')
    expected=bounded_bytes(checksum,1024).decode().split()[0]
    if not re.fullmatch('[a-f0-9]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('History checksum mismatch')
    data=json.loads(raw)
    if data.get('schema')!='pi-control.deploy-history/v1' or data.get('source_generation')!='legacy-sd':raise ValueError('Unsupported history import')
    rows=data.get('events')
    if not isinstance(rows,list) or len(rows)>MAX_EVENTS or len(rows)!=data.get('event_count'):raise ValueError('Invalid history count')
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or not re.fullmatch('legacy-[a-f0-9]{24}',row.get('event_id','')) or row['event_id'] in ids:raise ValueError('Invalid/duplicate history id')
        if row.get('kind')!='deploy' or row.get('source_generation')!='legacy-sd' or row.get('historical_only') is not True or row.get('rollback_available') is not False:raise ValueError('Invalid historical flags')
        if type(row.get('timestamp')) is not int or not 0<row['timestamp']<1e12:raise ValueError('Invalid history timestamp')
        if not isinstance(row.get('message'),str) or len(row['message'])>800:raise ValueError('Invalid history message')
        ids.add(row['event_id'])
    return [{k:r[k] for k in ('event_id','timestamp','kind','message','source_generation','historical_only','rollback_available')} | {'module':'legacy-bundle','level':r.get('level','info')} for r in rows]


class Ledger:
    def __init__(self,path,generation):
        self.path=Path(path);self.generation=generation

    def read(self):
        if not self.path.exists():return []
        data=checked_json(self.path)
        if data.get('schema')!=1 or not isinstance(data.get('events'),list) or len(data['events'])>MAX_EVENTS:raise ValueError('Invalid ledger')
        return data['events']

    def _write(self,rows):
        if len(rows)>MAX_EVENTS:raise ValueError('Deploy ledger full; archive explicitly before new writes')
        raw=json.dumps({'schema':1,'events':rows},ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>MAX_BYTES:raise ValueError('Deploy ledger too large')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        tmp=self.path.with_suffix('.tmp')
        if self.path.is_symlink() or tmp.is_symlink():raise ValueError('Unsafe ledger path')
        with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o644),'wb') as handle:
            os.chmod(tmp,0o644);handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.replace(tmp,self.path)
        descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)

    def import_legacy(self,path):
        import fcntl
        incoming=validate_import(Path(path))
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            rows=self.read();seen={r['event_id'] for r in rows}
            additions=[r for r in incoming if r['event_id'] not in seen]
            if additions:self._write(sorted(rows+additions,key=lambda r:r['timestamp']))
        return len(additions)

    def record(self,module,release,source_hash,outcome):
        import fcntl
        if not re.fullmatch('[a-z][a-z0-9-]{0,31}',module) or not re.fullmatch('[a-f0-9]{64}',source_hash):raise ValueError('Invalid deploy identity')
        if not re.fullmatch('[A-Za-z0-9._-]{1,100}',release) or outcome not in ('installed','failed','rolled-back'):raise ValueError('Invalid deploy outcome')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            rows=self.read()
            row=dict(event_id=uuid.uuid4().hex,timestamp=int(time.time()),kind='deploy',module=module,release=release,
                     source_hash=source_hash,source_generation=self.generation,historical_only=False,
                     outcome=outcome,message=f'{module}: {outcome} · {release}',level='error' if outcome=='failed' else 'info')
            self._write(rows+[row])
        return row
