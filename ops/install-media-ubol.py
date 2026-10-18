"""Install only the official Web Store uBOL policy; do not overwrite other policies."""
import json
import os
from pathlib import Path
import time

if os.geteuid()!=0:raise SystemExit('Run with sudo')
extension='ddkjiahejlhfcafbddmgiahcphecmpfh'
dest=Path('/etc/chromium/policies/managed/pi-media-ubol.json')
policy={'ExtensionSettings':{extension:{'installation_mode':'force_installed','update_url':'https://clients2.google.com/service/update2/crx'}},
        '3rdparty':{'extensions':{extension:{'defaultFiltering':'optimal','disableFirstRunPage':True}}}}
dest.parent.mkdir(parents=True,exist_ok=True)
for p in dest.parent.glob('*.json'):
    if p==dest:continue
    old=json.loads(p.read_text())
    if extension in old.get('ExtensionSettings',{}) or 'ExtensionInstallForcelist' in old:
        raise SystemExit('Existing extension policy requires review: '+str(p))
backup=Path('/var/lib/pi-media-setup')/time.strftime('%Y%m%dT%H%M%S')
backup.mkdir(parents=True,mode=0o700)
if dest.exists():(backup/'policy-before.json').write_bytes(dest.read_bytes())
else:(backup/'policy-was-absent').touch()
(backup/'restore.sh').write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nif [ -f policy-before.json ]; then install -m 0644 policy-before.json /etc/chromium/policies/managed/pi-media-ubol.json; else rm -f /etc/chromium/policies/managed/pi-media-ubol.json; fi\n')
(backup/'restore.sh').chmod(0o700)
dest.write_text(json.dumps(policy,indent=2)+'\n');dest.chmod(0o644)
print('Official uBOL Web Store policy installed for Chromium on this Pi.')
print('Recovery:',str(backup/'restore.sh'))
