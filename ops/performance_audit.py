"""Read-only Pi audit: host block writes are NOT NAND wear/lifetime counters."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

UNITS = ('piwifi-web.service', 'piwifi-observer.service')

def read(path):
    try: return Path(path).read_text().strip()
    except OSError: return None

def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=15)
    return p.stdout.strip() if p.returncode == 0 else None

def processes():
    result = {}
    for folder in Path('/proc').glob('[0-9]*'):
        try:
            io = dict(line.split(': ', 1) for line in (folder/'io').read_text().splitlines())
            result[int(folder.name)] = dict(name=(folder/'comm').read_text().strip(),
                                           write_bytes=int(io['write_bytes']), wchar=int(io['wchar']))
        except (OSError, ValueError, KeyError): pass
    return result

def unit(name):
    group = Path('/sys/fs/cgroup/system.slice') / name
    raw = read(group/'cpu.stat') or ''
    cpu = dict(line.split() for line in raw.splitlines())
    pids = (read(group/'cgroup.procs') or '').splitlines()
    rss = pss = 0
    for pid in pids:
        for line in (read('/proc/'+pid+'/smaps_rollup') or '').splitlines():
            if line.startswith('Rss:'): rss += int(line.split()[1]) * 1024
            if line.startswith('Pss:'): pss += int(line.split()[1]) * 1024
    return dict(usage_usec=int(cpu.get('usage_usec', 0)), rss=rss, pss=pss, pids=pids,
                memory_current=read(group/'memory.current'), io_stat=read(group/'io.stat'))

def snapshot():
    stats = list(map(int, (read('/sys/block/mmcblk0/stat') or '').split()))
    return dict(timestamp=time.time(), uptime=float(read('/proc/uptime').split()[0]),
                written_bytes=stats[6]*512, read_bytes=stats[2]*512,
                units={name:unit(name) for name in UNITS}, processes=processes())

def main():
    start = snapshot()
    intervals = []
    previous = start
    for _ in range(3):
        time.sleep(30)
        now = snapshot()
        elapsed = now['timestamp'] - previous['timestamp']
        intervals.append(dict(seconds=round(elapsed, 2), sd_written_bytes=now['written_bytes']-previous['written_bytes'],
                              services={n:dict(cpu_one_core_percent=round((now['units'][n]['usage_usec']-previous['units'][n]['usage_usec'])/elapsed/10000, 3),
                                               pss_bytes=now['units'][n]['pss'],rss_bytes=now['units'][n]['rss']) for n in UNITS}))
        previous = now
    elapsed = now['timestamp'] - start['timestamp']
    top = []
    for pid, process in now['processes'].items():
        old = start['processes'].get(pid)
        if old and old['name'] == process['name']:
            delta = process['write_bytes'] - old['write_bytes']
            if delta > 0: top.append(dict(pid=pid,name=process['name'],write_bytes=delta))
    config = {}
    for name in ('/etc/systemd/journald.conf', '/etc/fstab', '/etc/systemd/zram-generator.conf'):
        config[name] = [line for line in (read(name) or '').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    for folder in ('/etc/systemd/journald.conf.d','/etc/systemd/zram-generator.conf.d'):
        for p in Path(folder).glob('*.conf'):
            config[str(p)] = p.read_text().strip()
    kernel = command(['journalctl','-k','-b','--no-pager','-o','cat']) or ''
    errors = [line for line in kernel.splitlines() if re.search(r'I/O error|Buffer I/O|EXT4-fs error|mmc.*(?:error|timeout)|under.?voltage', line, re.I)]
    health = {}
    for attr in ('type','name','manfid','oemid','date','life_time','pre_eol_info'):
        health[attr] = read('/sys/block/mmcblk0/device/'+attr)
    result = dict(seconds=round(elapsed,2), cores=os.cpu_count(), intervals=intervals,
                  sd_written_bytes=now['written_bytes']-start['written_bytes'],
                  sd_write_bytes_since_boot=now['written_bytes'],uptime_seconds=round(now['uptime']),
                  top_process_writes=sorted(top,key=lambda p:p['write_bytes'],reverse=True)[:10],
                  card=health,kernel_error_count=len(errors),kernel_errors=errors[-20:],
                  journal_size=command(['journalctl','--disk-usage']),
                  journal_location=command(['du','-sh','/var/log/journal','/run/log/journal']),
                  observer_size=command(['du','-sh','/var/lib/piwifi-observer']),
                  observer_files={p.name:p.stat().st_size for p in Path('/var/lib/piwifi-observer').glob('*') if p.is_file()},
                  swaps=read('/proc/swaps'),zram_backing=read('/sys/block/zram0/backing_dev'),
                  zram_backing_stats=read('/sys/block/zram0/bd_stat'),zram_memory_stats=read('/sys/block/zram0/mm_stat'),
                  loop_backing=read('/sys/block/loop0/loop/backing_file'),
                  mount_options=command(['findmnt','-no','SOURCE,FSTYPE,OPTIONS','/']), config=config)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
