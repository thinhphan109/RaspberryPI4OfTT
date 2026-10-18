import importlib.machinery
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml

class SyncTests(unittest.TestCase):
    def load(self):
        loader=importlib.machinery.SourceFileLoader('dns_sync_test',str(Path(__file__).resolve().parents[1]/'helper/piwifi-dns-sync'))
        m=importlib.util.module_from_spec(importlib.util.spec_from_loader('dns_sync_test',loader));loader.exec_module(m)
        return m

    def scenario(self,ip,fail=False):
        m=self.load()
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'config.yaml';initial=yaml.safe_dump({'dns':{'bind_hosts':['127.0.0.1','192.168.0.106']}})
            config.write_text(initial)
            opened=open;calls=[]
            def fake_open(name,*args,**kwargs):return opened(Path(directory)/'lock' if name=='/run/lock/piwifi-dns-sync.lock' else name,*args,**kwargs)
            def run(args):
                calls.append(args)
                if args[0]=='ip':return json.dumps([{'addr_info':[{'local':ip}]}])
                if fail and '--check-config' in args:raise RuntimeError('bad config')
                return ''
            with patch.object(m,'CONFIG',config),patch.object(m,'run',side_effect=run),patch('builtins.open',side_effect=fake_open),patch.object(m.sys,'argv',['sync']):
                if fail:
                    with self.assertRaises(RuntimeError):m.main()
                    self.assertEqual(config.read_text(),initial)
                else:m.main()
            return calls,yaml.safe_load(config.read_text())

    def test_same_ip_no_write_or_restart(self):
        calls,_=self.scenario('192.168.0.106');self.assertEqual(len(calls),1)
    def test_new_ip_updates_after_stop_before_start(self):
        calls,data=self.scenario('192.168.10.44')
        self.assertEqual(data['dns']['bind_hosts'],['127.0.0.1','192.168.10.44'])
        self.assertLess(calls.index(['systemctl','stop','adguardhome']),calls.index(['systemctl','start','adguardhome']))
    def test_ap_not_claimed(self):
        _,data=self.scenario('192.168.50.1');self.assertEqual(data['dns']['bind_hosts'],['127.0.0.1'])
    def test_bad_config_restores(self):self.scenario('192.168.10.44',True)
