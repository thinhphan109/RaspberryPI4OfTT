#!/usr/bin/python3 -B
"""Controlled AP hardware check with an independent timed Wi-Fi restoration.

Run only after deploying network-r1. Runtime-only autoconnect changes simulate
having no eligible known network; no credentials or persistent profiles edited.
The restore timer is armed and verified before any connectivity change.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/run/pi-control-fallback-live-20261102')
SCRIPT = ROOT / 'run.py'
UNIT = 'pi-control-fallback-live-20261102'
ENV = {**os.environ, 'LC_ALL': 'C'}


def run(*args, timeout=30):
    return subprocess.run(list(args), check=True, text=True, capture_output=True,
                          timeout=timeout, env=ENV).stdout.strip()


def write(name, value):
    path = ROOT / name
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o600); temporary.replace(path)


def profiles():
    return {v[0]: v[2] for line in run('nmcli','-t','-f','UUID,TYPE,AUTOCONNECT','connection','show').splitlines()
            if len(v := line.split(':')) == 3 and v[1] in ('wifi','802-11-wireless')}


def file_hashes():
    folder = Path('/etc/NetworkManager/system-connections')
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}


def device():
    lines = run('nmcli','-g','GENERAL.STATE,GENERAL.CON-UUID,GENERAL.CONNECTION,IP4.ADDRESS','device','show','wlan0').splitlines()
    return dict(code=int(lines[0].split()[0]), uuid=lines[1], profile=lines[2], ipv4=lines[3:])


def arm():
    if (ROOT / 'plan.json').exists(): raise RuntimeError('Existing test; inspect first')
    assert json.loads(Path('/var/lib/pi-control/control/modules.json').read_text())['network']['release'] == 'v1-ffcc192dfc5c1572'
    state = device(); assert state['code'] == 100 and state['profile'] != 'Pi-Fallback'
    bus = run('nmcli','-g','GENERAL.DBUS-PATH','device','show','wlan0')
    auto = shlex.split(run('busctl','get-property','org.freedesktop.NetworkManager',bus,
                          'org.freedesktop.NetworkManager.Device','Autoconnect'))
    assert auto[0] == 'b' and auto[1] in ('true','false')
    write('plan.json', dict(device=state, profiles=profiles(), hashes=file_hashes(),
                            device_bus=bus, device_autoconnect=auto[1], armed=time.time()))
    run('systemd-run','--collect','--unit='+UNIT+'-restore','--on-active=120s',
        '--timer-property=AccuracySec=1s','--property=RuntimeMaxSec=90s',
        '/usr/bin/python3','-B',str(SCRIPT),'restore')
    run('systemctl','is-active','--quiet',UNIT+'-restore.timer')
    run('systemd-run','--collect','--unit='+UNIT+'-apply','--on-active=3s',
        '--timer-property=AccuracySec=1s','--property=RuntimeMaxSec=90s',
        '/usr/bin/python3','-B',str(SCRIPT),'apply')
    print(json.dumps(dict(armed=True, restore_after_seconds=120, current=state)))


def apply():
    plan = json.loads((ROOT / 'plan.json').read_text())
    result = {'ok': False, 'started': time.time()}
    try:
        run('systemctl','is-active','--quiet',UNIT+'-restore.timer')
        with open('/run/piwifi-network.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            run('systemctl','stop','pi-control-network-guard.timer','pi-control-network-guard.service')
            for uuid, auto in plan['profiles'].items():
                if auto == 'yes': run('nmcli','connection','modify','--temporary','uuid',uuid,'connection.autoconnect','no')
            assert all(value == 'no' for value in profiles().values())
            run('nmcli','-w','10','device','disconnect','wlan0')
        # Run the installed guard, not a direct AP activation command.
        run('systemctl','start','pi-control-network-guard.service',timeout=60)
        result['guard'] = json.loads(Path('/run/piwifi-guard.json').read_text())
        result['device'] = device()
        result['radio'] = run('/usr/sbin/iw','dev','wlan0','info')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:18765/login',timeout=3) as response:
            result['dashboard_http'] = response.status
        result['persistent_profiles_unchanged'] = file_hashes() == plan['hashes']
        result['ok'] = (result['guard']['state'] == 'fallback' and result['device']['code'] == 100
                        and result['device']['profile'] == 'Pi-Fallback' and result['persistent_profiles_unchanged'])
    except Exception as exc:
        result['error'] = type(exc).__name__
    result['finished'] = time.time(); write('ap-result.json',result)


def restore():
    plan = json.loads((ROOT / 'plan.json').read_text())
    result = {'ok': False, 'started': time.time(), 'errors': []}
    def attempt(label, *args, timeout=8):
        try: return run(*args, timeout=timeout)
        except Exception as exc: result['errors'].append(label+':'+type(exc).__name__)
    try:
        # Restores only the runtime values saved before this test.
        for uuid, auto in plan['profiles'].items():
            attempt('profile','nmcli','-w','5','connection','modify','--temporary','uuid',uuid,'connection.autoconnect',auto)
        # A failed restoration of one flag must never skip reconnecting Wi-Fi.
        for _ in range(2):
            if attempt('reconnect','nmcli','-w','20','connection','up','uuid',
                       plan['device']['uuid'],'ifname','wlan0',timeout=25) is not None: break
        attempt('device-auto','busctl','set-property','org.freedesktop.NetworkManager',plan['device_bus'],
                'org.freedesktop.NetworkManager.Device','Autoconnect','b',plan['device_autoconnect'])
        result['device'] = device()
        result['profiles_restored'] = profiles() == plan['profiles']
        result['persistent_profiles_unchanged'] = file_hashes() == plan['hashes']
        result['ok'] = (result['device']['code'] == 100 and result['device']['uuid'] == plan['device']['uuid']
                        and result['profiles_restored'] and result['persistent_profiles_unchanged'])
    except Exception as exc:
        result['error'] = type(exc).__name__
    finally:
        attempt('guard-timer','systemctl','start','pi-control-network-guard.timer')
    result['finished'] = time.time(); write('restore-result.json',result)


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('root required')
    {'arm': arm, 'apply': apply, 'restore': restore}[sys.argv[1]]()
