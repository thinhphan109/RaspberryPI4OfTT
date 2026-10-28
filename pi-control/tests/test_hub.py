import json
import time
import unittest
from unittest.mock import patch
import app
import hub

class HubTests(unittest.TestCase):
    def setUp(self):
        app._read_cache.clear()
        app.app.config['TESTING']=True
        self.client=app.app.test_client()

    def login(self):
        with self.client.session_transaction() as session:
            session['logged_in']=True
            session['csrf']='hub-test'

    def test_private_hub_and_diagnostic_require_login(self):
        for path in ['/api/hub','/api/dns-check']:
            self.assertEqual(self.client.get(path).status_code,302)

    def test_diagnostic_csrf_and_expiry(self):
        self.login()
        self.assertEqual(self.client.post('/api/dns-check').status_code,403)
        self.assertEqual(self.client.get('/api/dns-check').status_code,400)
        with self.client.session_transaction() as session:
            session['dns_check']={'domain':'old.example.com','started':time.time()-61}
        with patch.object(hub,'query_seen') as lookup:
            self.assertEqual(self.client.get('/api/dns-check').status_code,400)
            lookup.assert_not_called()

    def test_diagnostic_is_session_bound_and_inconclusive_if_unseen(self):
        self.login()
        response=self.client.post('/api/dns-check',headers={'X-CSRF-Token':'hub-test'})
        domain=response.json['data']['domain']
        self.assertRegex(domain,r'^[0-9a-f]{24}\.example\.com$')
        self.assertEqual(self.client.post('/api/dns-check',headers={'X-CSRF-Token':'hub-test'}).status_code,429)
        with patch.object(hub,'query_seen',return_value=False) as lookup,patch.object(hub,'dns_probe',return_value=True):
            result=self.client.get('/api/dns-check').json['data']
            self.assertFalse(result['seen']);self.assertTrue(result['filtering'])
            self.assertEqual(result['status'],'unconfirmed')
            self.assertEqual(lookup.call_args.args[0],domain)
        other=app.app.test_client()
        with other.session_transaction() as session:session['logged_in']=True
        self.assertEqual(other.get('/api/dns-check').status_code,400)

    def test_diagnostic_distinguishes_filter_failure_from_verified_path(self):
        self.login()
        self.client.post('/api/dns-check',headers={'X-CSRF-Token':'hub-test'})
        for blocked,expected in [(False,'filter_error'),(True,'verified')]:
            with patch.object(hub,'query_seen',return_value=True),patch.object(hub,'dns_probe',return_value=blocked):
                result=self.client.get('/api/dns-check').json['data']
                self.assertEqual(result['status'],expected)
                self.assertIsInstance(result['checked_at'],int)

    def test_lan_urls_use_reported_ip_and_loopback_is_not_published(self):
        with patch.object(hub.subprocess,'run') as run:
            run.return_value.stdout='active'
            result=hub.applications({'ip':'192.168.10.44/24','active_ssid':'Other network'})
        self.assertEqual(result['ip'],'192.168.10.44')
        self.assertTrue(result['apps'][0]['lan_url'].startswith('http://192.168.10.44:'))
        self.assertIsNone(next(row for row in result['apps'] if row.get('loopback'))['lan_url'])

    def test_invalid_network_does_not_create_link(self):
        self.assertIsNone(hub.lan_ip({'ip':'javascript:alert(1)'}))

if __name__=='__main__':unittest.main()
