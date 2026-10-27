"""Durable render jobs; worker units run independently of the camera agent."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
from runtime_config import CONFIG, location

IDENT=re.compile(r'^\d{8}T\d{6}-[a-f0-9]{8}$')


def directory():return location('camera_state',Path.home()/'.local/state/pi-camera')/'render-jobs'


def job_path(ident,result=False):
    if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Invalid render job id')
    return directory()/(ident+('.result.json' if result else '.json'))


def read_private(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>65536:raise ValueError('Invalid render job file')
    with path.open('rb') as stream:raw=stream.read(65537)
    if len(raw)>65536:raise ValueError('Render job too large')
    return json.loads(raw)


def write_private(path,payload):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    if path.is_symlink() or tmp.is_symlink():raise ValueError('Unsafe job path')
    with tmp.open('w',encoding='utf-8') as handle:
        os.chmod(tmp,0o600);json.dump(payload,handle);handle.flush();os.fsync(handle.fileno())
    os.replace(tmp,path)


def unit_name(ident):
    job_path(ident)
    return 'pi-control-camera-render@'+ident+'.service'


def active(ident):
    result=subprocess.run(['systemctl','--user','is-active',unit_name(ident)],capture_output=True,text=True,timeout=3)
    return result.stdout.strip() in ('active','activating','reloading')


def submit(session):
    ident=session['id'];target=job_path(ident)
    if active(ident):raise ValueError('Job ghép đang chạy')
    job_path(ident,True).unlink(missing_ok=True)
    write_private(target,dict(schema=1,session=session))
    subprocess.run(['systemctl','--user','--no-block','start',unit_name(ident)],check=True,capture_output=True,timeout=5)
    return ident


def wait(ident):
    started=time.monotonic()
    while time.monotonic()-started<1830:
        path=job_path(ident,True)
        if path.exists():
            result=read_private(path)
            if result.get('id')!=ident or result.get('state') not in ('ready','incomplete'):raise ValueError('Invalid render result')
            return result
        if time.monotonic()-started>10 and not active(ident):raise ValueError('Worker ghép đã dừng; giữ ảnh gốc để thử lại')
        time.sleep(1)
    raise ValueError('Worker ghép quá thời hạn; kiểm tra nhật ký render')


def pending():
    result=[]
    for path in sorted(directory().glob('*.json'),reverse=True)[:64]:
        ident=path.stem
        if not IDENT.fullmatch(ident) or job_path(ident,True).exists():continue
        if active(ident):result.append(read_private(path)['session'])
    if len(result)>1:raise ValueError('Có nhiều worker ghép; kiểm tra trạng thái Camera')
    return result[0] if result else None


def validated_session(ident):
    if CONFIG is None:raise ValueError('Render worker requires modular installation')
    data=read_private(job_path(ident))
    if data.get('schema')!=1:raise ValueError('Invalid job schema')
    session=data.get('session',{})
    if session.get('id')!=ident:raise ValueError('Job id mismatch')
    target=session.get('target',{})
    from runtime_config import desktop_runtime
    base=desktop_runtime()/'pi-camera-trial' if target.get('trial') is True else Path(CONFIG['data_mount'])/'PiCamera'
    if Path(target.get('root',''))!=base or Path(session.get('folder',''))!=base/ident:raise ValueError('Render outside approved storage')
    if not target.get('trial') and (target.get('mount')!=CONFIG['data_mount'] or target.get('uuid')!=CONFIG['data_uuid']):raise ValueError('Render storage identity mismatch')
    for key in ('frames','bytes','started'):
        if type(session.get(key)) is not int or session[key]<0:raise ValueError('Invalid render counters')
    import camera_agent
    if Path(session['folder']).is_symlink():raise ValueError('Unsafe render directory')
    if not target.get('trial') and not any(m['path']==target['mount'] and m['uuid']==CONFIG['data_uuid'] for m in camera_agent.external_mounts()):raise ValueError('Approved data volume is not mounted')
    camera_agent.check_target(target)
    return session
