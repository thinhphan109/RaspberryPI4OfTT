"""Bounded same-user MPRIS controls. No app launching, URLs or browser/account reads."""
import hashlib
import json
import math
import re
import subprocess
import threading
import time

PATH='/org/mpris/MediaPlayer2'
PLAYER='org.mpris.MediaPlayer2.Player'
PROPERTIES='org.freedesktop.DBus.Properties'
NAME=re.compile(r'org\.mpris\.MediaPlayer2\.[A-Za-z0-9_][A-Za-z0-9_.-]{0,160}')
OWNER=re.compile(r':\d+\.\d+')


def unwrap(value):
    if isinstance(value,dict):
        if set(value)=={'type','data'}:return unwrap(value['data'])
        return {k:unwrap(v) for k,v in value.items()}
    if isinstance(value,list):return [unwrap(v) for v in value]
    return value


def bus(destination,path,interface,method,*arguments,timeout=1.2):
    try:
        result=subprocess.run(['busctl','--user',f'--timeout={timeout}s','--json=short','call',destination,path,interface,method,*arguments],
                              capture_output=True,text=True,timeout=timeout+.5,check=True)
    except (OSError,subprocess.SubprocessError):raise ValueError('Ứng dụng chưa phản hồi; kiểm tra app trên Pi rồi thử lại.') from None
    if len(result.stdout)>262144:raise ValueError('Ứng dụng trả dữ liệu quá lớn.')
    if not result.stdout.strip():return []
    try:
        result=unwrap(json.loads(result.stdout))
        if not isinstance(result,list):raise ValueError()
        return result
    except (ValueError,TypeError):raise ValueError('Chưa đọc được trạng thái ứng dụng.') from None


def valid(name,owner=None):
    if not isinstance(name,str) or not NAME.fullmatch(name):raise ValueError('Ứng dụng không hợp lệ.')
    if name.lower().split('.')[3] in ('chromium','chrome','firefox','brave','edge'):raise ValueError('Dùng điều khiển Media hiện có cho trình duyệt.')
    if owner is not None and (not isinstance(owner,str) or not OWNER.fullmatch(owner)):raise ValueError('Phiên ứng dụng không hợp lệ.')
    return name


def number(value,maximum):
    return min(maximum,max(0,value)) if type(value) in (float,int) and math.isfinite(value) else None


class NativePlayer:
    def __init__(self):
        self.lock=threading.RLock()

    def owner(self,name):
        valid(name)
        value=bus('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner','s',name)
        if len(value)!=1 or not isinstance(value[0],str) or not OWNER.fullmatch(value[0]):raise ValueError('Phiên ứng dụng chưa sẵn sàng.')
        return value[0]

    def check(self,name,owner):
        valid(name,owner)
        if self.owner(name)!=owner:raise ValueError('Ứng dụng đã khởi động lại. Bấm Quét ứng dụng để cập nhật.')

    def players(self):
        with self.lock:
            names=bus('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','ListNames')[0]
            if not isinstance(names,list):raise ValueError('Chưa đọc được danh sách ứng dụng.')
            rows=[];seen=set();deadline=time.monotonic()+3
            for name in sorted(n for n in names if isinstance(n,str) and NAME.fullmatch(n))[:16]:
                if time.monotonic()>deadline:break
                try:
                    valid(name);owner=self.owner(name)
                    process=bus('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID','s',owner)[0]
                    if process in seen:continue
                    label=bus(name,PATH,PROPERTIES,'Get','ss','org.mpris.MediaPlayer2','Identity')[0]
                    if not isinstance(label,str):continue
                except (ValueError,IndexError):continue
                seen.add(process);rows.append(dict(id=name,owner=owner,label=label[:100]))
            return {'players':rows,'message':'' if rows else 'Chưa có app hỗ trợ MPRIS đang mở trên Pi.'}

    def snapshot(self,name,owner):
        self.check(name,owner)
        props=bus(owner,PATH,PROPERTIES,'GetAll','s',PLAYER)[0]
        if not isinstance(props,dict):raise ValueError('Ứng dụng chưa cung cấp trạng thái phát.')
        meta=props.get('Metadata') or {}
        if not isinstance(meta,dict):meta={}
        artists=meta.get('xesam:artist') or []
        if not isinstance(artists,list):artists=[]
        controlled=props.get('CanControl') is True
        volume=number(props.get('Volume'),10)
        position=number(props.get('Position'),864000000000)
        duration=number(meta.get('mpris:length'),864000000000)
        return dict(id=name,owner=owner,title=str(meta.get('xesam:title') or 'Đang phát trên ứng dụng')[:200],
                    artist=', '.join(a[:80] for a in artists[:4] if isinstance(a,str))[:180],
                    playback=props.get('PlaybackStatus') if props.get('PlaybackStatus') in ('Playing','Paused','Stopped') else 'Unknown',
                    position=None if position is None else position/1000000,duration=None if duration is None else duration/1000000,
                    volume=None if volume is None else round(min(1,volume)*100),
                    can_play=controlled and props.get('CanPlay') is True,can_pause=controlled and props.get('CanPause') is True,
                    can_next=controlled and props.get('CanGoNext') is True,can_previous=controlled and props.get('CanGoPrevious') is True,
                    can_seek=controlled and props.get('CanSeek') is True,can_volume=controlled and volume is not None,
                    track=hashlib.sha256(str(meta.get('mpris:trackid') or '').encode()).hexdigest()[:16])

    def status(self,name,owner):
        with self.lock:return self.snapshot(name,owner)

    def command(self,name,owner,action,value=None):
        if action not in ('play','pause','next','previous','seek','volume'):raise ValueError('Thao tác ứng dụng không hợp lệ.')
        if action=='seek' and (type(value) not in (float,int) or value not in (-10,10)):raise ValueError('Chỉ tua ±10 giây.')
        if action=='volume' and (type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=100):raise ValueError('Âm lượng từ 0 đến 100%.')
        with self.lock:
            before=self.snapshot(name,owner)
            if not before['can_'+action]:raise ValueError('Ứng dụng chưa hỗ trợ thao tác này.')
            self.check(name,owner)  # Reject a restarted/reused well-known bus name before writing.
            if action=='volume':bus(owner,PATH,PROPERTIES,'Set','ssv',PLAYER,'Volume','d',str(value/100))
            elif action=='seek':bus(owner,PATH,PLAYER,'Seek','x',str(int(value*1000000)))
            else:bus(owner,PATH,PLAYER,{'play':'Play','pause':'Pause','next':'Next','previous':'Previous'}[action])
            deadline=time.monotonic()+1
            seek_target=None if before['position'] is None else max(0,before['position']+(value if action=='seek' else 0))
            if seek_target is not None and before['duration'] is not None:seek_target=min(seek_target,before['duration'])
            while True:
                after=self.snapshot(name,owner)
                confirmed=(after['playback']==('Playing' if action=='play' else 'Paused')) if action in ('play','pause') else (
                    abs(after['volume']-value)<=1 if action=='volume' and after['volume'] is not None else
                    after['track']==before['track'] and abs(after['position']-seek_target)<=2.5 if action=='seek' and after['position'] is not None and seek_target is not None else
                    after['track']!=before['track'] if action in ('next','previous') else False)
                if confirmed or time.monotonic()>=deadline:
                    after['receipt']={'state':'confirmed' if confirmed else 'unconfirmed','message':'Đã xác nhận trạng thái ứng dụng.' if confirmed else 'Đã gửi lệnh; chưa xác nhận thay đổi từ ứng dụng.'}
                    return after
                time.sleep(.1)
