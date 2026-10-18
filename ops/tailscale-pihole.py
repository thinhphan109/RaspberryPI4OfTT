"""Configure existing Pi-hole for this Pi's Tailscale IP with timed recovery."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

assert os.geteuid() == 0
run = lambda args: subprocess.run(args, check=True, capture_output=True, text=True)
status = json.loads(run(['tailscale', 'status', '--json']).stdout)
assert status['BackendState'] == 'Running', 'Authenticate Pi first'
ts_ip = next(ip for ip in status['TailscaleIPs'] if ':' not in ip)
assert ipaddress.ip_address(ts_ip) in ipaddress.ip_network('100.64.0.0/10')
config = Path('/etc/pihole/pihole.toml')
assert config.is_file() and not config.is_symlink()
snapshot = Path('/var/lib/tailscale-setup') / time.strftime('%Y%m%dT%H%M%SZ-pihole', time.gmtime())
snapshot.mkdir(mode=0o700)
backup = snapshot / 'pihole.toml'
shutil.copy2(config, backup)
recovery = snapshot / 'restore.sh'
recovery.write_text('#!/bin/sh\nset -eu\ncp -p ' + str(backup) + ' /etc/pihole/pihole.toml\nsystemctl restart pihole-FTL\n')
recovery.chmod(0o700)
unit = 'pihole-tailscale-recovery-' + str(int(time.time()))
run(['systemd-run', '--unit='+unit, '--on-active=120s', '/bin/sh', str(recovery)])
try:
    # Keep current LAN DNS working during migration. Bind only selected IPs so
    # NetworkManager can continue using its own DNS on fallback AP 192.168.50.1.
    changes = {
        'dns.listeningMode': 'NONE',
        'misc.dnsmasq_lines': json.dumps(['bind-dynamic', 'listen-address=127.0.0.1,192.168.0.106,'+ts_ip]),
        # Bind web independently of changing physical IPs and interface startup.
        # Nonempty CivetWeb ACL denies clients without a matching allow rule.
        'webserver.port': '18853',
        'webserver.acl': '+127.0.0.1,+192.168.0.101,+100.64.0.0/10',
    }
    for key, value in changes.items():
        run(['pihole-FTL', '--config', key, value])
    run(['pihole-FTL', 'dnsmasq-test'])
    run(['systemctl', 'restart', 'pihole-FTL'])
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(15):
        try:
            with http.open('http://127.0.0.1:18853/admin/', timeout=3) as response:
                assert response.status == 200
            break
        except Exception:
            if attempt == 14:
                raise
            time.sleep(1)
    assert run(['dig', '@'+ts_ip, 'doubleclick.net', '+short']).stdout.strip() == '0.0.0.0'
    assert run(['dig', '@192.168.0.106', 'example.com', '+short']).stdout.strip()
    run(['systemctl', 'is-active', '--quiet', 'pihole-FTL', 'piwifi-web', 'piwifi-observer', 'cloudflared'])
    run(['systemctl', 'stop', unit+'.timer'])
    (snapshot / 'result.json').write_text(json.dumps({'ip':ts_ip, 'health':'passed', 'snapshot':str(snapshot)}))
    print(json.dumps({'ip':ts_ip, 'health':'passed', 'snapshot':str(snapshot)}))
except BaseException:
    run(['/bin/sh', str(recovery)])
    run(['systemctl', 'stop', unit+'.timer'])
    raise
