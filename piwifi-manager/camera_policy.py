"""Small, deterministic position gate; never sends commands to the printer."""
import math
import re
from collections import deque


def number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} phải từ {low} đến {high}')
    return float(value)


def regions(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Chọn đủ vùng đầu in và vùng bàn in')
    result = []
    for item in value:
        if not isinstance(item, list) or len(item) != 4:
            raise ValueError('Vùng ảnh không hợp lệ')
        x, y, w, h = [number(v, 0, 1, 'Tọa độ') for v in item]
        if w < .04 or h < .04 or w * h < .005 or x + w > 1.000001 or y + h > 1.000001:
            raise ValueError('Vùng ảnh quá nhỏ hoặc nằm ngoài khung hình')
        result.append([x, y, w, h])
    a,b=result
    overlap=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))*max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
    if overlap/min(a[2]*a[3],b[2]*b[3])>.5:
        raise ValueError('Hai vùng cần tách biệt: một vùng đầu in, một vùng bàn in')
    return result


class PositionGate:
    """Require leave -> return -> settle; one shot until a genuine departure."""
    def __init__(self, threshold=.06, settle=.6, departure=.4, cooldown=2):
        self.threshold = threshold
        self.settle = settle
        self.departure = departure
        self.cooldown = cooldown
        self.armed = False
        self.inside_since = None
        self.outside_since = None
        self.last_shot = -float('inf')
        self.phase = 'waiting_departure'
        self.samples = deque(maxlen=360)

    def feed(self, scores, now):
        if not isinstance(scores, (list, tuple)) or len(scores) != 2 or any(
                not math.isfinite(s) or s < 0 for s in scores):
            self.inside_since = self.outside_since = None
            self.phase = 'invalid_frame'
            return False
        self.samples.append((now, tuple(scores)))
        inside = all(s <= self.threshold for s in scores)
        outside = any(s > self.threshold * 1.5 for s in scores)
        if outside:
            self.inside_since = None
            if self.outside_since is None:
                self.outside_since = now
            if now - self.outside_since >= self.departure:
                self.armed = True
            self.phase = 'waiting_return' if self.armed else 'leaving'
        elif inside:
            self.outside_since = None
            if self.inside_since is None:
                self.inside_since = now
            self.phase = ('cooldown' if now-self.last_shot < self.cooldown else 'settling') if self.armed else 'waiting_departure'
            if self.armed and now - self.inside_since >= self.settle and now - self.last_shot >= self.cooldown:
                self.armed = False
                self.last_shot = now
                self.phase = 'captured'
                return True
        else:
            self.inside_since = self.outside_since = None
            self.phase = 'waiting_return' if self.armed else 'waiting_departure'
        return False

    def diagnostics(self, now):
        # Bounded RAM only; inspecting never feeds or arms the gate.
        recent = [scores for at,scores in self.samples if now-at <= 30]
        return dict(phase=self.phase, armed=self.armed,
                    threshold=round(self.threshold*100, 1),
                    departure_threshold=round(self.threshold*150, 1),
                    recent_max=[round(max(s[i] for s in recent)*100,1) for i in range(2)] if recent else None,
                    samples=len(recent))


class ViewerPower:
    """RAM-only viewer leases survive missing pagehide; recording always wins."""
    TTL = 15
    GRACE = 5
    LIMIT = 32

    def __init__(self, automatic=True):
        self.automatic = automatic
        self.viewers = {}
        self.paused = False
        self.idle_since = None

    def prune(self, now):
        self.viewers = {key:expiry for key,expiry in self.viewers.items() if expiry > now}

    def watch(self, viewer, watching, now):
        if not isinstance(viewer,str) or not re.fullmatch('[a-f0-9]{64}',viewer) or type(watching) is not bool:
            raise ValueError('Phiên xem camera không hợp lệ')
        self.prune(now)
        if watching:
            if viewer not in self.viewers and len(self.viewers) >= self.LIMIT:
                raise ValueError('Đã đạt giới hạn số phiên xem')
            # A manual stop is respected until all previous viewers leave.
            if not self.viewers:
                self.paused = False
            self.viewers[viewer] = now+self.TTL
        else:
            self.viewers.pop(viewer,None)

    def manual(self, enabled):
        self.paused = not enabled
        self.idle_since = None

    def decision(self, recording, now):
        self.prune(now)
        if recording:
            self.idle_since = None
            return True
        if not self.automatic:
            self.idle_since = None
            return None
        if self.viewers and not self.paused:
            self.idle_since = None
            return True
        if self.idle_since is None:
            self.idle_since = now
        return False if now-self.idle_since >= self.GRACE else None
