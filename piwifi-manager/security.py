"""Bounded SSH observations; never claims a complete 24-hour audit."""
import collections
import json
import re
import subprocess
import time
import threading

_lock=threading.Lock()
_cached=None
_when=0
_records=collections.deque(maxlen=2000)
_cursor=None
_started=int(time.time())

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=2)
    if p.returncode:raise OSError('Không đọc được dữ liệu SSH')
    if len(p.stdout)>1048576:raise OSError('Dữ liệu vượt giới hạn')
    return p.stdout

def parse_record(entry):
    text=entry.get('MESSAGE','')
    if not isinstance(text,str):return None
    match=re.search(r'(Accepted|Failed) (password|publickey) for (?:invalid user )?(\S+) from (\S+)',text)
    if not match:return None
    return dict(timestamp=int(entry['__REALTIME_TIMESTAMP'])/1000000,user=match[3],ip=match[4],kind='login' if match[1]=='Accepted' else 'failed',method=match[2],cursor=entry.get('__CURSOR'))

def status():
    global _cached,_when,_cursor
    with _lock:
        now=time.monotonic()
        if _cached is not None and now-_when<60:return _cached
        result=dict(timestamp=int(time.time()),supported=False,complete=False,coverage_since=_started,reason='Chỉ dữ liệu đã quan sát; tối đa 200 bản ghi mỗi lượt, không bảo đảm đủ 24 giờ',active_connections_count=None,active_ips=[],failed_observed_count=None,last_logins=[])
        try:
            # ss with no process lookup; records are TCP connections, not authenticated sessions.
            output=command(['ss','-Htn','state','established','sport = :22'])
            peers=[line.split()[-1].rsplit(':',1)[0].strip('[]') for line in output.splitlines() if line.split()]
            result.update(active_connections_count=len(peers),active_ips=sorted(set(peers)))
        except (OSError,subprocess.TimeoutExpired):pass
        try:
            args=['journalctl','-u','ssh','-u','sshd','-n','200','--no-pager','-o','json','--output-fields=MESSAGE,__REALTIME_TIMESTAMP,__CURSOR']
            if _cursor:args.append('--after-cursor='+_cursor)
            entries=[json.loads(line) for line in command(args).splitlines() if line.startswith('{')]
            known={r['cursor'] for r in _records}
            for entry in entries:
                row=parse_record(entry)
                if row and row['cursor'] not in known:_records.append(row);known.add(row['cursor'])
            if entries:_cursor=entries[-1].get('__CURSOR')
            records=[r for r in _records if r['timestamp']>=time.time()-86400]
            failed=[r for r in records if r['kind']=='failed']
            counts=collections.Counter(r['ip'] for r in failed)
            result.update(supported=True,failed_observed_count=len(failed),top_failed_ip=counts.most_common(1)[0][0] if counts else None,last_logins=[{k:v for k,v in r.items() if k!='cursor'} for r in records if r['kind']=='login'][-5:][::-1])
        except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired):
            result['reason']='Chưa đọc được nhật ký SSH; không kết luận không có lỗi'
        _cached=result;_when=now
        return result
