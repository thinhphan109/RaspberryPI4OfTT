"""Run as root on Pi. Keeps credentials in memory and prints only health results."""
import json
import pathlib
import subprocess
import time
import urllib.request

base = 'http://127.0.0.1:18853/api'
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
password = pathlib.Path('/home/thinh/.config/pihole-trial/admin-password').read_text().strip()
request = urllib.request.Request(base + '/auth', data=json.dumps({'password': password}).encode(), headers={'Content-Type': 'application/json'})
with http.open(request, timeout=10) as response:
    session = json.load(response)['session']
assert session['valid'], 'API login failed'
sid = session['sid']
with http.open(urllib.request.Request(base + '/stats/summary', headers={'sid': sid}), timeout=10) as response:
    summary = json.load(response)
print('API login: PASS; blocklist:', summary.get('gravity', {}), flush=True)
http.open(urllib.request.Request(base + '/auth', method='DELETE', headers={'sid': sid}), timeout=10).close()

pid = int(subprocess.check_output(['systemctl', 'show', 'pihole-FTL', '-p', 'MainPID', '--value']))
def sample():
    stat = pathlib.Path(f'/proc/{pid}/stat').read_text().split()
    io = dict(line.split(':', 1) for line in pathlib.Path(f'/proc/{pid}/io').read_text().splitlines())
    return int(stat[13]) + int(stat[14]), int(io['write_bytes'])

start = sample()
begin = time.monotonic()
time.sleep(60)
end = sample()
elapsed = time.monotonic() - begin
import os
cpu = (end[0] - start[0]) / os.sysconf('SC_CLK_TCK') / elapsed * 100
status = pathlib.Path(f'/proc/{pid}/status').read_text().splitlines()
rss = next(line for line in status if line.startswith('VmRSS:'))
print(json.dumps({'seconds': round(elapsed, 1), 'cpu_percent_one_core': round(cpu, 3), 'process_write_bytes_delta': end[1]-start[1], 'ram': rss}), flush=True)
config = pathlib.Path('/etc/pihole/pihole.toml')
import tomllib
settings = tomllib.loads(config.read_text())
assert settings['dhcp']['active'] is False
assert settings['dns']['queryLogging'] is False
assert settings['database']['maxDBdays'] == 0
assert settings['ntp']['sync']['active'] is False
assert settings['webserver']['session']['restore'] is False
assert settings['files']['database'].startswith('/run/pihole-trial/')
print('Configuration assertions: PASS')
