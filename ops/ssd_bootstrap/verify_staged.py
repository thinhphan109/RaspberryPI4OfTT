#!/usr/bin/python3 -B
"""Exercise the real ARM kit inside a temporary fake root; no host installation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(kit):
    sys.path.insert(0,str(kit));import bootstrap
    manifest,_=bootstrap.verify_bundle(kit)
    config=dict(schema=1,desktop_user='thinh',desktop_uid=1000,desktop_home='/home/thinh',generation='a'*32,
                root_uuid='11111111-1111',data_uuid='22222222-2222',data_mount='/srv/pi-control',camera_device='auto')
    with tempfile.TemporaryDirectory(prefix='sandbox-',dir=kit.parent) as temp:
        root=Path(temp)
        result=bootstrap.install(kit,root,config,['dashboard','media','camera','dns'],True,False)
        metadata=root/'var/lib/pi-control/control/modules.json';before=metadata.read_bytes()
        sys.path.insert(0,str(kit/'files/dashboard'));from deployment_history import Ledger
        history=next(kit.glob('deploy-history-legacy-sd-*.json'))
        ledger=Ledger(root/'var/lib/pi-control/control/deploy-history.json',config['generation'])
        imported=ledger.import_legacy(history);again=ledger.import_legacy(history)
        assert imported==67 and again==0 and metadata.read_bytes()==before
        assert len([r for r in ledger.read() if r.get('historical_only')])==67
        import yaml
        settings=yaml.safe_load((root/'etc/pi-control/dns/AdGuardHome.yaml').read_text())
        settings['http']['address']='127.0.0.1:18856';settings['dns']['port']=53556
        settings['querylog']['dir_path']=str(root/'dns-check/querylog');settings['statistics']['dir_path']=str(root/'dns-check/statistics')
        (root/'dns-check/work').mkdir(parents=True)
        check=root/'dns-check.yaml';check.write_text(yaml.safe_dump(settings))
        binary=kit/'files/dns/AdGuardHome';binary.chmod(0o755)
        # --check-config parses settings; does not start a server or change production config.
        process=subprocess.run([str(binary),'-c',str(check),'-w',str(root/'dns-check/work'),'--check-config'],capture_output=True,text=True,timeout=30)
        if process.returncode:raise RuntimeError('AdGuard configuration validation failed: '+process.stderr[:500])
        unitfiles=[p for p in (root/'etc/systemd').rglob('*') if p.suffix in ('.service','.timer') and p.is_file() and not p.is_symlink()]
        verify=subprocess.run(['systemd-analyze','verify','--man=no',*[str(p) for p in unitfiles]],capture_output=True,text=True,timeout=30)
        if verify.returncode:raise RuntimeError('Unit validation failed: '+verify.stderr[:2000])
        return dict(ok=True,modules=len(manifest['modules']),files=len(manifest['files']),units=len(unitfiles),legacy_events=imported,
                    repeat_import=again,arm_adguard_config='passed',host_install=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kit',type=Path);args=parser.parse_args()
    print(json.dumps(run(args.kit.resolve())))
