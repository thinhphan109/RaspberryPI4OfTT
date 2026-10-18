"""Bounded local preferences, RAM listening history and restart-safe sleep latch."""
from collections import deque
import math
import re
import time

class PlaybackPolicy:
    def __init__(self):
        self.disliked={}
        self.repeat=dict(enabled=True,hours=3)
        self.history=deque(maxlen=500)
        self.sleep=None
        self.deadline=None
        self.tracked=''

    def configure_repeat(self,d):
        if not isinstance(d,dict) or type(d.get('enabled')) is not bool or type(d.get('hours')) is not int or not 1<=d['hours']<=24:
            raise ValueError('Chống lặp cần bật/tắt và số giờ từ 1 đến 24')
        self.repeat={k:d[k] for k in ('enabled','hours')}

    def dislike(self,ident,title):
        if not re.fullmatch(r'[\w-]{11}',ident,flags=re.ASCII):raise ValueError('Mã video không hợp lệ')
        if ident not in self.disliked and len(self.disliked)>=200:
            raise ValueError('Tối đa 200 bài không thích; bỏ chặn một bài trước khi thêm')
        self.disliked[ident]=str(title or ident)[:300]

    def reason(self,ident,automatic=True,now=None):
        if ident in self.disliked:return 'Bài không thích'
        now=time.monotonic() if now is None else now
        if automatic and self.repeat['enabled'] and any(i==ident and now-at<self.repeat['hours']*3600 for i,at in self.history):
            return 'Đã nghe gần đây'
        return ''

    def observe(self,ident,now=None):
        if ident and ident!=self.tracked:
            self.history.append((ident,time.monotonic() if now is None else now));self.tracked=ident

    def start_sleep(self,minutes,volume,now=None,wall=None):
        if type(minutes) is not int or not 1<=minutes<=720:raise ValueError('Hẹn giờ từ 1 đến 720 phút')
        now=time.monotonic() if now is None else now
        wall=time.time() if wall is None else wall
        self.sleep=dict(ends_at=wall+minutes*60,duration=minutes*60,volume=volume)
        self.deadline=now+minutes*60

    def cancel_sleep(self):
        self.sleep=None;self.deadline=None

    def sleep_state(self,now=None):
        if self.sleep is None:return dict(active=False,expired=False,remaining=0)
        now=time.monotonic() if now is None else now
        remaining=max(0,self.deadline-now)
        return dict(active=remaining>0,expired=remaining<=0,remaining=math.ceil(remaining),ends_at=self.sleep['ends_at'],fade_seconds=min(120,self.sleep['duration']))

    def sleep_cap(self,now=None):
        s=self.sleep_state(now)
        if not self.sleep:return 100
        return min(100,self.sleep['volume']*min(1,s['remaining']/s['fade_seconds']))

    def dump(self):
        return dict(disliked=self.disliked,repeat=self.repeat,sleep=self.sleep)

    def load(self,d):
        if not isinstance(d,dict):return
        if isinstance(d.get('disliked'),dict):
            for ident,title in list(d['disliked'].items())[:200]:
                try:self.dislike(ident,title)
                except ValueError:pass
        try:self.configure_repeat(d.get('repeat'))
        except ValueError:pass
        s=d.get('sleep')
        if isinstance(s,dict) and all(type(s.get(k)) in (int,float) and math.isfinite(s[k]) for k in ('ends_at','duration','volume')):
            if 60<=s['duration']<=43200 and 0<=s['volume']<=100:
                self.sleep={k:s[k] for k in ('ends_at','duration','volume')}
                # Never extend a persisted timer beyond its original duration.
                self.deadline=time.monotonic()+max(0,min(s['duration'],s['ends_at']-time.time()))

    def summary(self):
        return dict(repeat=dict(self.repeat,history_count=len(self.history)),
                    disliked=[dict(id=i,title=t) for i,t in self.disliked.items()],sleep=self.sleep_state())
