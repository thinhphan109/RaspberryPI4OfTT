"""Fixed local audio/BlueZ controls; user-session privileges only."""
import json
import math
import os
import re
import subprocess
import threading
import time

LOCK=threading.Lock()
JOB=dict(running=False,message='')
CACHE=None
CACHE_AT=0

def run(args,timeout=4,stdin=None):
    try:
        p=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=timeout,env=dict(os.environ,LC_ALL='C',NO_COLOR='1'))
    except subprocess.TimeoutExpired:raise ValueError('Thao tác quá thời gian; kiểm tra thiết bị hoặc hộp thoại trên Pi')
    if p.returncode:raise ValueError((p.stderr or p.stdout or 'Lệnh bị từ chối').strip()[-300:])
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',p.stdout)

def nodes():
    result=[]
    for item in json.loads(run(['pw-dump'])):
        info=item.get('info',{});p=info.get('props',{});kind=p.get('media.class')
        if kind not in ('Audio/Sink','Audio/Source'):continue
        name=p.get('node.name','')
        if not name or name.startswith('easyeffects_'):continue
        result.append(dict(id=item['id'],name=name,label=p.get('node.nick') or p.get('node.description') or name,kind='output' if kind=='Audio/Sink' else 'input'))
    return result

def default_name(kind):
    special='@DEFAULT_AUDIO_SINK@' if kind=='output' else '@DEFAULT_AUDIO_SOURCE@'
    try:
        text=run(['wpctl','inspect',special]);m=re.search(r'node.name = "([^"]+)"',text)
        return m.group(1) if m else ''
    except ValueError:return ''

def bluetooth():
    try:
        show=run(['bluetoothctl','show'])
        text=run(['bluetoothctl','devices']);devices=[]
        for address,label in re.findall(r'^Device ([0-9A-F:]{17}) (.+)$',text,re.M)[:30]:
            info=run(['bluetoothctl','info',address])
            devices.append(dict(address=address,label=label[:150],paired='Paired: yes' in info,connected='Connected: yes' in info,trusted='Trusted: yes' in info))
        return dict(available=True,powered='Powered: yes' in show,devices=devices,error='')
    except (ValueError,OSError) as exc:return dict(available=False,powered=False,devices=[],error=str(exc)[:200])

def status(force=False):
    global CACHE,CACHE_AT
    if not force and CACHE is not None and time.monotonic()-CACHE_AT<5:
        return dict(CACHE,job=dict(JOB))
    errors=[];devices=[]
    try:
        devices=nodes()
        for d in devices:
            text=run(['wpctl','get-volume',str(d['id'])]);m=re.search(r'Volume: ([\d.]+)',text)
            d.update(volume=round(float(m.group(1))*100) if m else 0,muted='MUTED' in text)
        defaults={k:default_name(k) for k in ('input','output')}
    except (ValueError,OSError) as exc:errors.append(str(exc));defaults={}
    CACHE=dict(devices=devices,defaults=defaults,bluetooth=bluetooth(),errors=errors)
    CACHE_AT=time.monotonic()
    return dict(CACHE,job=dict(JOB))

def checked_node(d):
    ident=d.get('id');kind=d.get('kind')
    if type(ident) is not int or kind not in ('input','output'):raise ValueError('Thiết bị âm thanh không hợp lệ')
    item=next((n for n in nodes() if n['id']==ident and n['kind']==kind),None)
    if item is None:raise ValueError('Thiết bị đã thay đổi; làm mới danh sách')
    return item

def background(action,address=None):
    global CACHE_AT
    try:
        if action=='scan':
            try:run(['bluetoothctl','--timeout','6','scan','on'],timeout=9)
            finally:
                try:run(['bluetoothctl','scan','off'])
                except ValueError:
                    # --timeout may already have released its discovery session.
                    if 'Discovering: yes' in run(['bluetoothctl','show']):raise
        elif action=='pair':
            # Only explicitly selected device; do not silently trust devices.
            text=run(['bluetoothctl','--agent','NoInputNoOutput','--timeout','15','pair',address],timeout=18)
            if 'Pairing successful' not in text:raise ValueError('Chưa ghép nối. Với thiết bị cần PIN/xác nhận, hoàn tất trực tiếp trên desktop Pi.')
        else:
            text=run(['bluetoothctl','--timeout','10',action,address],timeout=13)
            if 'Failed' in text or 'not available' in text:raise ValueError(text[-220:])
        with LOCK:JOB.update(running=False,message='Đã hoàn tất '+dict(scan='quét',pair='ghép nối',connect='kết nối',disconnect='ngắt kết nối')[action])
    except Exception as exc:
        with LOCK:JOB.update(running=False,message=str(exc)[:250])
    finally:CACHE_AT=0

def dispatch(d):
    global CACHE_AT
    action=d.get('action','status')
    if action=='status':return status()
    if action in ('scan','pair','connect','disconnect'):
        address=d.get('address')
        if action!='scan':
            if not isinstance(address,str) or not re.fullmatch(r'[0-9A-F]{2}(?::[0-9A-F]{2}){5}',address):raise ValueError('Địa chỉ Bluetooth không hợp lệ')
            known=bluetooth()['devices']
            if not any(x['address']==address for x in known):raise ValueError('Chỉ chọn thiết bị đã có trong danh sách quét')
        with LOCK:
            if JOB['running']:raise ValueError('Đang có thao tác Bluetooth; chờ hoàn tất')
            JOB.update(running=True,message='Đang '+dict(scan='quét trong 6 giây',pair='ghép nối',connect='kết nối',disconnect='ngắt kết nối')[action])
        threading.Thread(target=background,args=(action,address),daemon=True).start()
        return status()
    if action=='power':
        if type(d.get('enabled')) is not bool:raise ValueError('Cần giá trị bật/tắt')
        text=run(['bluetoothctl','power','on' if d['enabled'] else 'off'])
        if 'Failed' in text:raise ValueError(text[-200:])
    elif action in ('default','volume','mute'):
        item=checked_node(d);ident=str(item['id'])
        if action=='default':
            # Keep EasyEffects following the physical default. Its virtual sink
            # is deliberately not selectable, avoiding feedback loops.
            run(['wpctl','set-default',ident])
            schema='com.github.wwmm.easyeffects.streamoutputs' if item['kind']=='output' else 'com.github.wwmm.easyeffects.streaminputs'
            key='use-default-output-device' if item['kind']=='output' else 'use-default-input-device'
            run(['gsettings','set',schema,key,'true'])
        elif action=='volume':
            v=d.get('value')
            if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100:raise ValueError('Âm lượng từ 0 đến 100%')
            run(['wpctl','set-volume',ident,str(v/100)])
        else:
            if type(d.get('muted')) is not bool:raise ValueError('Cần giá trị bật/tắt tiếng')
            run(['wpctl','set-mute',ident,'1' if d['muted'] else '0'])
    else:raise ValueError('Thao tác âm thanh không được hỗ trợ')
    CACHE_AT=0
    return status(force=True)
