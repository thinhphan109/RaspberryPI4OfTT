"""Low-cost, read-only Linux telemetry; no extra runtime dependencies."""
import os
import shutil
import socket
import subprocess
import threading
import time
import json
from pathlib import Path
from runtime_config import unit as runtime_unit

_lock = threading.Lock()
_last = None
_network_last = {}
_process_last = {}
_cache = {}
_cache_lock = threading.Lock()

def primary_interface():
    routes = (_read('/proc/net/route') or '').splitlines()[1:]
    candidates=[]
    for row in routes:
        parts=row.split()
        if len(parts)>7 and parts[1]=='00000000' and int(parts[3],16)&1:
            candidates.append((int(parts[6]),parts[0]))
    return min(candidates)[1] if candidates else 'wlan0'

def fresh(snapshot):
    """Cheap request-time reads against observer baselines; no commands or writes."""
    result=dict(snapshot)
    temp=_read('/sys/class/thermal/thermal_zone0/temp')
    freq=_read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')
    result['temperature']=round(int(temp)/1000,1) if temp else None
    result['frequency_mhz']=round(int(freq)/1000) if freq else None
    memory={}
    for row in (_read('/proc/meminfo') or '').splitlines():
        k,v=row.split(':',1);memory[k]=int(v.split()[0])*1024
    total=memory.get('MemTotal',0);used=max(0,total-memory.get('MemAvailable',total))
    result['ram']=dict(total=total,used=used,percent=round(100*used/total,1) if total else None)
    fields=list(map(int,(_read('/proc/stat') or 'cpu 0 0 0 0').splitlines()[0].split()[1:9]))
    ticks,idle=sum(fields),sum(fields[3:5]);old=snapshot.get('cpu_ticks')
    if old and ticks>old[0]:result['cpu']=round(100*(1-(idle-old[1])/(ticks-old[0])),1)
    elapsed=time.monotonic()-snapshot.get('monotonic',time.monotonic())
    baseline={n['name']:n for n in snapshot.get('network',[])}
    networks=[]
    for row in (_read('/proc/net/dev') or '').splitlines()[2:]:
        name,raw=row.split(':',1);name=name.strip()
        if name=='lo':continue
        values=raw.split();rx,tx=int(values[0]),int(values[8]);old=baseline.get(name)
        valid=old and elapsed>=1 and rx>=old['rx'] and tx>=old['tx']
        networks.append(dict(name=name,rx=rx,tx=tx,rx_rate=round((rx-old['rx'])/elapsed) if valid else old.get('rx_rate') if old and rx>=old['rx'] else None,tx_rate=round((tx-old['tx'])/elapsed) if valid else old.get('tx_rate') if old and tx>=old['tx'] else None))
    result['network']=networks
    result['primary_interface']=primary_interface()
    return result

def cached(key, ttl, function):
    with _cache_lock:
        now = time.monotonic()
        old = _cache.get(key)
        if old and now-old[0] < ttl: return old[1]
        value = function()
        _cache[key] = (now, value)
        return value

_cache = {}
_cache_lock = threading.Lock()

def cached(key, ttl, function):
    with _cache_lock:
        now = time.monotonic()
        old = _cache.get(key)
        if old and now-old[0] < ttl: return old[1]
        value = function()
        _cache[key] = (now, value)
        return value


def power_status():
    try:
        p = subprocess.run(['/usr/bin/vcgencmd', 'get_throttled'], capture_output=True, text=True, timeout=2)
        if p.returncode:
            raise ValueError()
        flags = int(p.stdout.strip().split('=')[1], 16)
        return dict(available=True, raw=hex(flags), undervoltage=bool(flags & 1),
                    frequency_capped=bool(flags & 2), throttled=bool(flags & 4), soft_temp_limit=bool(flags & 8),
                    undervoltage_occurred=bool(flags & (1 << 16)), throttled_occurred=bool(flags & (1 << 18)),
                    frequency_capped_occurred=bool(flags & (1 << 17)), soft_temp_limit_occurred=bool(flags & (1 << 19)),
                    status='danger' if flags & 15 else 'warning' if flags & (15 << 16) else 'healthy')
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return dict(available=False, status='unknown', undervoltage=None, throttled=None)

def network_rates(now):
    global _network_last
    result = []
    for line in (_read('/proc/net/dev') or '').splitlines()[2:]:
        name, values = line.split(':', 1)
        name = name.strip()
        if name == 'lo':
            continue
        values = values.split()
        rx, tx = int(values[0]), int(values[8])
        old = _network_last.get(name)
        elapsed = now - old[0] if old and rx >= old[1] and tx >= old[2] else 0
        result.append(dict(name=name, rx=rx, tx=tx,
                           rx_rate=round(max(0, rx-old[1])/elapsed) if elapsed > 0 else None,
                           tx_rate=round(max(0, tx-old[2])/elapsed) if elapsed > 0 else None))
        _network_last[name] = (now, rx, tx)
    _network_last = {n['name']: _network_last[n['name']] for n in result}
    return result

def processes(now):
    global _process_last
    result, latest = [], {}
    ticks = os.sysconf('SC_CLK_TCK')
    for path in Path('/proc').glob('[0-9]*'):
        try:
            raw = (path / 'stat').read_text()
            end = raw.rfind(')')
            fields = raw[end + 2:].split()
            key = (int(path.name), fields[19])  # pid + start time protects against reuse
            used = int(fields[11]) + int(fields[12])
            old = _process_last.get(key)
            cpu = max(0, (used-old[1])/ticks/(now-old[0])*100) if old and now > old[0] else None
            latest[key] = (now, used)
            result.append(dict(pid=key[0], name=raw[raw.find('(')+1:end], cpu=round(cpu, 1) if cpu is not None else None,
                               rss=max(0, int(fields[21])) * os.sysconf('SC_PAGE_SIZE')))
        except (OSError, ValueError, IndexError):
            continue
    _process_last = latest
    return sorted(result, key=lambda p: (p['cpu'] or 0, p['rss']), reverse=True)[:10]

def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None

def service_states():
    services = []
    for unit in ('piwifi-web', 'NetworkManager', 'ssh', 'piwifi-guard.timer', 'piwifi-observer'):
        try:
            p = subprocess.run(['systemctl', 'is-active', runtime_unit(unit)], capture_output=True, text=True, timeout=2)
            state = p.stdout.strip() or 'unknown'
        except (OSError, subprocess.TimeoutExpired): state = 'unknown'
        services.append(dict(name=unit, state=state))
    return services

def collect():
    global _last
    with _lock:
        now = time.monotonic()
        fields = list(map(int, (_read('/proc/stat') or 'cpu 0 0 0 0').splitlines()[0].split()[1:9]))
        total, idle = sum(fields), sum(fields[3:5])
        cpu = None
        if _last and total > _last[0]:
            cpu = round(100 * (1 - (idle - _last[1]) / (total - _last[0])), 1)
        _last = (total, idle, now)
    memory = {}
    for line in (_read('/proc/meminfo') or '').splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0]) * 1024
    ram_total = memory.get('MemTotal', 0)
    ram_used = max(0, ram_total - memory.get('MemAvailable', ram_total))
    disks = []
    seen = set()
    for line in (_read('/proc/mounts') or '').splitlines():
        device, mount, *_ = line.split()
        mount = mount.replace('\\040', ' ')
        if not device.startswith('/dev/') or device in seen:
            continue
        seen.add(device)
        try:
            usage = shutil.disk_usage(mount)
            disks.append(dict(device=device, mount=mount, total=usage.total, used=usage.used, free=usage.free,
                              percent=round(100 * usage.used / usage.total, 1)))
        except OSError:
            pass
    services = cached('services', 60, service_states)
    temp = _read('/sys/class/thermal/thermal_zone0/temp')
    uptime = _read('/proc/uptime')
    try:
        guard = json.loads(_read('/run/piwifi-guard.json') or '{}')
    except ValueError:
        guard = {}
    return dict(hostname=socket.gethostname(), temperature=round(int(temp)/1000, 1) if temp else None,
                cpu=cpu, cores=os.cpu_count(), load=list(os.getloadavg()),
                ram=dict(total=ram_total, used=ram_used, percent=round(100*ram_used/ram_total, 1) if ram_total else None),
                swap=dict(total=memory.get('SwapTotal', 0), used=memory.get('SwapTotal', 0)-memory.get('SwapFree', 0)),
                uptime=int(float(uptime.split()[0])) if uptime else None, disks=disks, services=services,
                timestamp=int(time.time()), guard=guard, power=cached('power', 10, power_status),
                frequency_mhz=round(int(_read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'))/1000)
                if _read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq') else None,
                network=network_rates(now), processes=cached('processes', 30, lambda: processes(now)),
                cpu_ticks=[total,idle], monotonic=now, primary_interface=primary_interface(),
                boot_id=_read('/proc/sys/kernel/random/boot_id'), history_storage='ram')
