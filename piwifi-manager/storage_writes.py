"""Observed block-device writes: RAM sampling, five-minute durable checkpoints.

Counts host writes, not NAND wear. Existing pre-install writes are not backfilled.
Only this module's storage statistics opt into periodic persistence.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

CHECKPOINT_SECONDS = 300
DAY_OFFSET = 7 * 3600  # Calendar days in Vietnam, independent of host timezone.


def system_sample():
    root = Path('/sys/block/mmcblk0')
    cid = (root / 'device/cid').read_text().strip()
    if not cid:
        raise ValueError('Không đọc được định danh thẻ SD')
    values = (root / 'stat').read_text().split()
    return dict(device=hashlib.sha256(cid.encode()).hexdigest(),
                name='mmcblk0', model=(root / 'device/name').read_text().strip(),
                boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                counter=int(values[6]) * 512,
                uptime=float(Path('/proc/uptime').read_text().split()[0]),
                timestamp=time.time())


class WriteTracker:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=3, check_same_thread=False)
        os.chmod(self.path, 0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (device TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS buckets (device TEXT, resolution TEXT, bucket INTEGER, written REAL, duration REAL, PRIMARY KEY(device,resolution,bucket))')
        self.db.commit()
        self.state = None
        self.pending = {}
        self.rate = None
        self.last_checkpoint = time.monotonic()
        self.last_saved = None
        self.error = ''
        self.dirty = False
        self.day_changed = False
        self.retry_after = 0

    @staticmethod
    def bucket(ts, period):
        offset = DAY_OFFSET if period == 86400 else 0
        return math.floor((ts + offset) / period) * period - offset

    def _allocate(self, start, end, amount, duration):
        for resolution, period, keep in [('minute', 60, 7*86400), ('hour', 3600, 90*86400), ('day', 86400, None)]:
            if end <= start:
                parts = [(self.bucket(end, period), 1.0)]
            else:
                first = self.bucket(max(start, end-keep) if keep else start, period)
                parts = []
                for bucket in range(first, self.bucket(end, period)+1, period):
                    overlap = max(0, min(end, bucket+period)-max(start, bucket))
                    if overlap:
                        parts.append((bucket, overlap/(end-start)))
            for bucket, fraction in parts:
                key = (resolution, bucket)
                previous = self.pending.setdefault(key, [0.0, 0.0])
                previous[0] += amount*fraction
                previous[1] += duration*fraction

    def sample(self, current):
        if current['counter'] < 0 or not all(math.isfinite(current[k]) for k in ('uptime','timestamp')):
            raise ValueError('Bộ đếm ghi không hợp lệ')
        with self.lock:
            if self.state is None or self.state['device'] != current['device']:
                if self.dirty:
                    self.checkpoint(force=True)
                row = self.db.execute('SELECT payload FROM state WHERE device=?', (current['device'],)).fetchone()
                self.state = json.loads(row[0]) if row else dict(current, started=current['timestamp'], total=0, resets=0, saved_at=None)
                self.pending = {}
                self.last_saved = self.state.get('saved_at')
                self.rate = None
                if not row:
                    self.dirty = True
                    self.checkpoint(force=True)
                    return
            previous = self.state
            if self.bucket(current['timestamp'],86400)>self.bucket(previous['timestamp'],86400):
                self.day_changed = True
            same_boot = previous['boot'] == current['boot']
            if same_boot and current['counter'] >= previous['counter']:
                delta = current['counter'] - previous['counter']
                duration = max(0, current['uptime']-previous['uptime'])
                start = previous['timestamp']
                self.rate = delta/duration if 0 < duration <= 30 else None
            elif not same_boot:
                delta = current['counter']
                duration = max(0, current['uptime'])
                start = max(previous['timestamp'], current['timestamp']-duration)
                self.rate = None
            else:
                # Same-boot counter reset: establish a new baseline, never a spike.
                delta = 0
                duration = 0
                start = current['timestamp']
                previous['resets'] += 1
                self.rate = None
            self._allocate(start, current['timestamp'], delta, duration)
            self.state = dict(previous, **current)
            self.state['total'] += delta
            self.dirty = True

    def checkpoint(self, force=False):
        with self.lock:
            now = time.monotonic()
            if not self.dirty or (not force and (now<self.retry_after or (not self.day_changed and now-self.last_checkpoint < CHECKPOINT_SECONDS))):
                return False
            saved = time.time()
            payload = dict(self.state, saved_at=saved)
            try:
                with self.db:
                    for (resolution, bucket), (written, duration) in self.pending.items():
                        self.db.execute('INSERT INTO buckets VALUES (?,?,?,?,?) ON CONFLICT(device,resolution,bucket) DO UPDATE SET written=written+excluded.written,duration=duration+excluded.duration',
                                        (self.state['device'],resolution,bucket,written,duration))
                    self.db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(device) DO UPDATE SET payload=excluded.payload',
                                    (self.state['device'],json.dumps(payload)))
                    self.db.execute("DELETE FROM buckets WHERE resolution='minute' AND bucket<?", (int(saved)-7*86400,))
                    self.db.execute("DELETE FROM buckets WHERE resolution='hour' AND bucket<?", (int(saved)-90*86400,))
            except Exception:
                self.error = 'Chưa lưu được thống kê; dữ liệu mới vẫn ở RAM'
                self.last_checkpoint = now
                self.retry_after = now+CHECKPOINT_SECONDS
                raise
            self.pending.clear()
            self.state = payload
            self.last_saved = saved
            self.last_checkpoint = now
            self.dirty = False
            self.day_changed = False
            self.retry_after = 0
            self.error = ''
            return True

    @staticmethod
    def compact(rows, limit=360):
        size = max(1, math.ceil(len(rows)/limit))
        points = []
        for index in range(0, len(rows), size):
            group = rows[index:index+size]
            amount = sum(r['written'] for r in group)
            duration = sum(r['duration'] for r in group)
            points.append(dict(timestamp=group[-1]['timestamp'], written=amount,
                               rate=amount/duration if duration > 0 else None))
        return points

    def _rows(self, resolution, since):
        rows = {b:[w,d] for b,w,d in self.db.execute('SELECT bucket,written,duration FROM buckets WHERE device=? AND resolution=? AND bucket>=? ORDER BY bucket',
                                                   (self.state['device'],resolution,since))}
        for (kind, bucket), (written, duration) in self.pending.items():
            if kind == resolution and bucket >= since:
                value = rows.setdefault(bucket,[0.0,0.0])
                value[0] += written
                value[1] += duration
        return [dict(timestamp=b,written=v[0],duration=v[1]) for b,v in sorted(rows.items())]

    def query(self, hours=24, days=30):
        if hours not in (1,24,168) or days not in (30,90,0):
            raise ValueError('Khoảng thống kê không hợp lệ')
        with self.lock:
            if not self.state:
                return dict(available=False,error='Chưa có mẫu ghi SD')
            now = self.state['timestamp']
            rate_rows = self._rows('hour' if hours == 168 else 'minute', now-hours*3600)
            day_rows = self._rows('day', self.bucket(now,86400)-(days-1)*86400 if days else 0)
            return dict(available=True,name=self.state['name'],model=self.state['model'],
                        started=self.state['started'],timestamp=now,boot_bytes=self.state['counter'],
                        total_bytes=self.state['total'],rate=self.rate,saved_at=self.last_saved,
                        checkpoint_seconds=CHECKPOINT_SECONDS,error=self.error,
                        rate_history=self.compact(rate_rows),daily_history=self.compact(day_rows),
                        daily_grouped=len(day_rows)>360,resets=self.state['resets'])

    def close(self):
        with self.lock:
            self.checkpoint(force=True)
            self.db.close()
