import importlib.machinery
import importlib.util
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch,Mock
import app
import state

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    loader=importlib.machinery.SourceFileLoader(name,str(path))
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader(name,loader))
    loader.exec_module(module)
    return module

def guard_module():
    original=importlib.machinery.SourceFileLoader.exec_module
    def redirected(loader,module):
        if loader.name=='piwifi_helper': module.__dict__.update(vars(load('test_guard_helper',ROOT/'helper/piwifi-helper')))
        else: original(loader,module)
    with patch.object(importlib.machinery.SourceFileLoader,'exec_module',redirected):
        return load('test_guard',ROOT/'helper/piwifi-guard')

class DashboardTests(unittest.TestCase):
    def setUp(self):
        app._read_cache.clear()
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patcher=patch.object(state,'ROOT',Path(temporary.name))
        patcher.start();self.addCleanup(patcher.stop)
        app.app.config['TESTING']=True
        self.client=app.app.test_client()
    def authenticate(self):
        with self.client.session_transaction() as s: s['logged_in']=True;s['csrf']='test-token'
    def test_api_requires_login(self):
        for endpoint in ('/api/metrics','/api/status','/api/scan'):
            self.assertEqual(self.client.get(endpoint).status_code,302)
    def test_real_metrics(self):
        self.authenticate();response=self.client.get('/api/metrics');data=response.json['data']
        self.assertEqual(response.status_code,200);self.assertGreater(data['ram']['total'],0)
        self.assertTrue(data['disks']);self.assertLessEqual(data['ram']['percent'],100)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
    def test_utf8_dashboard_and_ssid_escape(self):
        self.authenticate()
        payload={'profiles':[],'active':'wifi','active_ssid':'Nhà <script>alert(1)</script>','ip':'','gateway':'','dns':['1.1.1.1','8.8.8.8'],'signal':50,'hotspot':{'configured':True,'active':False,'ssid':'RaspPI4OfTT','ip':'192.168.50.1','security':'WPA-PSK','priority':-50,'password_mask':'••••••••'}}
        with patch.object(app,'helper',return_value=payload):
            r=self.client.get('/');html=r.data.decode('utf-8',errors='strict')
            self.assertEqual(r.status_code,200);self.assertIn('Fallback Hotspot',html)
            self.assertIn('Nhiệt độ',html);self.assertIn('••••••••',html)
            self.assertIn('&lt;script&gt;',html);self.assertNotIn('rasp/',html)
    def test_csrf_prevents_mutation(self):
        self.authenticate()
        with patch.object(app,'helper') as helper:
            self.client.post('/wifi/delete',data={'name':'test'})
            helper.assert_not_called()
    def test_non_wifi_rejected(self):
        h=load('test_helper',ROOT/'helper/piwifi-helper')
        with patch.object(h,'nm',return_value='uuid\n802-3-ethernet\neth0'):
            with self.assertRaises(RuntimeError):h.delete_profile('wired')
    def test_ssid_byte_limit(self):
        h=load('test_utf8_helper',ROOT/'helper/piwifi-helper')
        with patch.object(h,'nm') as nm:
            with self.assertRaises(RuntimeError):h.save_wifi('ệ'*12,'password123',80)
            nm.assert_not_called()
    def test_recovery_needs_active_ipv4(self):
        h=load('test_recover',ROOT/'helper/piwifi-helper')
        with patch.object(h,'get_active',return_value='new'),patch.object(h,'validate_profile',side_effect=lambda s:s),patch.object(h,'nm',side_effect=lambda *a:'100 (connected)' if 'GENERAL.STATE' in a else '192.168.1.30/24'),patch.object(h,'connect_profile') as connect:
            h.recover_profile('old','new');connect.assert_not_called()
        with patch.object(h,'get_active',return_value='--'),patch.object(h,'connect_profile') as connect:
            h.recover_profile('old','new');connect.assert_called_once_with('old',recovery=False)
        def validate(name):
            if name=='deleted':raise RuntimeError('missing')
            return name
        with patch.object(h,'get_active',return_value='other'),patch.object(h,'validate_profile',side_effect=validate),patch.object(h,'connect_profile') as connect:
            h.recover_profile('old','deleted');connect.assert_called_once_with('old',recovery=False)
    def test_network_lock_excludes_second_writer(self):
        h=load('test_lock',ROOT/'helper/piwifi-helper')
        original_open=open
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'network.lock'
            with patch('builtins.open',side_effect=lambda *a,**kw:original_open(path,'a')):
                with h.network_lock():
                    with self.assertRaises(RuntimeError):
                        with h.network_lock():pass
    def test_hotspot_metadata_never_reads_password(self):
        h=load('test_metadata',ROOT/'helper/piwifi-helper')
        with patch.object(h,'nm',return_value='uuid\nRaspPI4OfTT\nap\nwpa-psk\n192.168.50.1/24\n-50') as nm,patch.object(h,'get_active',return_value='home'):
            info=h.hotspot_info();self.assertEqual(info['password_mask'],'••••••••')
            self.assertNotIn('password',info)
            self.assertNotIn('802-11-wireless-security.psk',nm.call_args.args)
    def test_active_client_wifi_is_preserved(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='home'),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'preserved');connect.assert_not_called()
    def test_hotspot_client_and_unknown_preserved(self):
        g=guard_module()
        for count,expected in ((2,'hotspot-in-use'),(None,'clients-unknown')):
            with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=count),patch.object(g.helper,'connect_profile') as connect:
                self.assertEqual(g.run()['state'],expected);connect.assert_not_called()
    def test_failed_ap_scan_preserves_hotspot(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=0),patch.object(g,'previous_state',return_value={'empty_checks':1}),patch.object(Path,'read_text',return_value='0'),patch.object(g.helper,'command',side_effect=RuntimeError('unsupported')),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'ap-scan-unavailable');connect.assert_not_called()
    def test_empty_ap_wait_and_return(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=0),patch.object(g,'previous_state',return_value={}),patch.object(Path,'read_text',return_value='0'),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'waiting-no-clients');connect.assert_not_called()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=0),patch.object(g,'previous_state',return_value={}),patch.object(Path,'read_text',return_value='9999999999'),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'hotspot-grace');connect.assert_not_called()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=0),patch.object(g,'previous_state',return_value={'empty_checks':1}),patch.object(Path,'read_text',return_value='0'),patch.object(g.helper,'command',return_value='\tSSID: Home'),patch.object(g,'candidates',return_value=[('home','uuid')]),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'returned-to-wifi');connect.assert_called_once_with('uuid')
    def test_client_arrives_before_return(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',side_effect=[0,1]),patch.object(g,'previous_state',return_value={'empty_checks':1}),patch.object(Path,'read_text',return_value='0'),patch.object(g.helper,'command',return_value='SSID: Home'),patch.object(g,'candidates',return_value=[('home','uuid')]),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'client-arrived');connect.assert_not_called()
    def test_failed_return_restores_ap(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='Pi-Fallback'),patch.object(g.helper,'nm',return_value='enabled'),patch.object(g,'clients',return_value=0),patch.object(g,'previous_state',return_value={'empty_checks':1}),patch.object(Path,'read_text',return_value='0'),patch.object(g.helper,'command',return_value='SSID: Home'),patch.object(g,'candidates',return_value=[('home','uuid')]),patch.object(g.helper,'connect_profile',side_effect=[RuntimeError('wrong password'),None]) as connect:
            self.assertEqual(g.run()['state'],'return-failed-restored-ap');self.assertEqual(connect.call_args.args,('Pi-Fallback',))
    def test_disconnected_fallback_and_disabled_radio(self):
        g=guard_module()
        with patch.object(g.helper,'get_active',return_value='--'),patch.object(g.helper,'nm',side_effect=lambda *a:'enabled' if a==('radio','wifi') else '30 (disconnected)'),patch.object(g,'candidates',return_value=[('first','u1'),('second','u2')]),patch.object(g.helper,'connect_profile',side_effect=[RuntimeError(),RuntimeError(),None]) as connect:
            self.assertEqual(g.run()['state'],'fallback');self.assertEqual(connect.call_args.args,('Pi-Fallback',))
        with patch.object(g.helper,'get_active',return_value='--'),patch.object(g.helper,'nm',return_value='disabled'),patch.object(g.helper,'connect_profile') as connect:
            self.assertEqual(g.run()['state'],'radio-disabled');connect.assert_not_called()

if __name__=='__main__':unittest.main()
