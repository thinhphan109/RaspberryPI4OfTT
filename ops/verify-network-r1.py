#!/usr/bin/python3 -B
"""Compare staged sources and exercise NM parsing without any network writes."""
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


def verify(kit):
    changes = {}
    for name in ('network', 'dashboard'):
        old = Path('/opt/pi-control') / name / 'current'
        new = kit / 'files' / name
        def hashes(folder):
            return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                    and p.suffix != '.pyc' and p.name != 'installer-units.json'}
        before, after = hashes(old), hashes(new)
        changes[name] = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    helper = kit / 'files/network/helper/piwifi-helper'
    original = importlib.machinery.SourceFileLoader.exec_module
    def redirect(loader, module):
        if loader.name == 'piwifi_helper': module.__dict__.update(vars(load('network_r1_helper', helper)))
        else: original(loader, module)
    with patch.object(importlib.machinery.SourceFileLoader, 'exec_module', redirect):
        guard = load('network_r1_guard', kit / 'files/network/helper/piwifi-guard')
    with patch.object(guard.helper, 'connect_profile', side_effect=AssertionError('Read-only verification: network mutation blocked')):
        status = guard.connection_status()
        result = guard.run()
        assert status['ready'] and result['state'] == 'preserved'
    return dict(ok=True, source_changes=changes, actual_nm_read=status,
                guard=result, network_mutations=False)


if __name__ == '__main__': print(json.dumps(verify(Path(sys.argv[1]).resolve()), ensure_ascii=False))
