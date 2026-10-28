import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import observer
import metrics
import state
import mcp_server
from test_dashboard import load, ROOT

class OperationsTests(unittest.TestCase):
    def setUp(self):
        app._read_cache.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.patch = patch.object(state, 'ROOT', self.folder)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.dbpatch = patch.object(observer, 'DB', self.folder/'history.db')
        self.dbpatch.start(); self.addCleanup(self.dbpatch.stop)
        self.client = app.app.test_client()
    def login(self):
        with self.client.session_transaction() as s:
            s['logged_in'] = True; s['csrf'] = 'ops-token'
    def test_new_apis_require_authentication(self):
        for path in ('/api/history', '/api/events', '/api/operation', '/api/deployments'):
            self.assertEqual(self.client.get(path).status_code, 302)
    def test_reader_cannot_write(self):
        with observer.connect() as db:
            db.execute('INSERT INTO samples VALUES (?,?)',(int(time.time()),'{}'))
        import sqlite3
        with observer.reader() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM samples')
    def test_cache_reuses_reads_and_does_not_share_mutable_result(self):
        self.login()
        with patch.object(app,'helper',return_value={'active':'home'}) as helper:
            self.client.get('/api/status');self.client.get('/api/status')
            helper.assert_called_once_with('status')
        result=app.cached_read('network',10,lambda:None);result['active']='changed'
        self.assertEqual(app.cached_read('network',10,lambda:None)['active'],'home')
    def test_operation_exposes_server_clock(self):
        self.login()
        state.write('operation.json',{'id':'a','stage':'confirmed','updated':100})
        before=int(time.time())
        value=self.client.get('/api/operation').json['data']['server_time']
        self.assertGreaterEqual(value,before)
        self.assertLessEqual(value,int(time.time()))
    def test_restart_and_rollback_require_csrf(self):
        self.login()
        with patch.object(app, 'helper') as helper:
            self.client.post('/service/restart', data={'name':'piwifi-web'})
            self.client.post('/deploy/rollback')
            self.client.post('/api/operation/ack', data={'id':'a'})
            helper.assert_not_called()
    def test_connect_page_uses_detached_operation(self):
        self.login()
        operation={'id':'c'*24,'stage':'queued','target':'wifi','steps':[]}
        with patch.object(app,'helper',return_value=operation) as helper:
            response=self.client.post('/wifi/connect',data={'csrf':'ops-token','name':'home','ssid':'Nhà Việt'})
        helper.assert_called_once_with('submit-operation','connect','home')
        self.assertEqual(response.status_code,200)
        html=response.data.decode('utf-8')
        self.assertIn('operation-steps',html);self.assertIn('Nhà Việt',html)
    def test_restart_allowlist(self):
        helper = load('ops_helper', ROOT/'helper/piwifi-helper')
        with patch.object(helper, 'command') as command:
            for unit in ('NetworkManager', 'ssh', 'piwifi-web;reboot'):
                with self.assertRaises(RuntimeError): helper.service_restart(unit)
            command.assert_not_called()
    def test_event_history_is_bounded_and_unicode(self):
        for i in range(505): state.event('test', 'Nhiệt độ · '+str(i))
        entries=state.read('events.json')
        self.assertEqual(len(entries),500)
        self.assertEqual(entries[0]['message'],'Nhiệt độ · 5')
    def test_wrong_operation_cannot_ack(self):
        helper = load('ack_helper', ROOT/'helper/piwifi-helper')
        state.write('operation.json', {'id':'a','stage':'awaiting-browser','target':'wifi'})
        with self.assertRaises(RuntimeError): helper.acknowledge_operation('b')
        with patch.object(helper,'get_active',return_value='other'),patch.object(helper,'validate_profile',return_value='other'):
            with self.assertRaises(RuntimeError): helper.acknowledge_operation('a')
        self.assertEqual(state.read('operation.json')['stage'],'awaiting-browser')
    def test_queue_failure_is_not_reported_success(self):
        helper=load('queue_helper',ROOT/'helper/piwifi-helper')
        with patch.object(helper,'validate_profile',return_value='uuid'),patch.object(helper,'command',side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):helper.submit_operation('connect','home')
        self.assertEqual(state.read('operation.json')['stage'],'failed')
    def test_execute_waits_for_browser_and_records_ipv4(self):
        helper=load('execute_helper',ROOT/'helper/piwifi-helper')
        operation='a'*24
        state.write('operation.json',{'id':operation,'target':'wifi','stage':'queued'})
        with patch.object(helper,'connect_profile') as connect,patch.object(helper,'nm',return_value='192.168.1.30/24'):
            helper.execute_operation(operation,'wifi')
        connect.assert_called_once_with('wifi')
        self.assertEqual(state.read('operation.json')['stage'],'awaiting-browser')
        self.assertEqual([s['stage'] for s in state.read('operation.json')['steps']],['connecting','address','awaiting-browser'])
        with patch.object(helper,'get_active',return_value='home'),patch.object(helper,'validate_profile',return_value='wifi'):
            self.assertTrue(helper.acknowledge_operation(operation)['confirmed'])
        self.assertEqual(state.read('operation.json')['stage'],'confirmed')
    def test_execute_failure_and_untrusted_operation(self):
        helper=load('execute_failed_helper',ROOT/'helper/piwifi-helper')
        operation='b'*24
        state.write('operation.json',{'id':operation,'target':'wifi','stage':'queued'})
        with patch.object(helper,'connect_profile',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):helper.execute_operation(operation,'wifi')
        self.assertEqual(state.read('operation.json')['stage'],'failed')
        with patch.object(helper,'connect_profile') as connect:
            with self.assertRaises(RuntimeError):helper.execute_operation(operation,'other')
            connect.assert_not_called()
    def test_history_buckets_preserve_peak(self):
        now=int(time.time())
        rows=[dict(timestamp=now-800+i,cpu=99 if i==0 else 1,ram=30,temperature=45) for i in range(800)]
        points=observer.bucket_history(rows)
        self.assertLessEqual(len(points),360)
        self.assertEqual(points[0]['cpu'],99)
    def test_hotspot_diagnostics_skip_external_probes(self):
        with patch.object(observer.subprocess,'run') as run,patch.object(observer.http.client,'HTTPConnection') as web:
            data=observer.diagnostics({'active':'Pi-Fallback','ip':'192.168.50.1/24'})
        run.assert_not_called()
        web.assert_called_once_with('127.0.0.1',18765,timeout=2)
        web.return_value.request.assert_called_once_with('GET','/login',headers={'Connection':'close'})
        self.assertEqual([l['state'] for l in data['layers'][2:5]],['na']*3)
    def test_throttling_flags_distinguish_current_from_past(self):
        from types import SimpleNamespace
        with patch.object(metrics.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='throttled=0x50000')):
            flags=metrics.power_status()
        self.assertFalse(flags['undervoltage']);self.assertFalse(flags['throttled'])
        self.assertTrue(flags['undervoltage_occurred']);self.assertTrue(flags['throttled_occurred'])
    def test_mcp_has_only_read_tools(self):
        tools=mcp_server.respond({'id':1,'method':'tools/list'})['result']['tools']
        self.assertEqual(len(tools),6)
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools))
        response=mcp_server.respond({'id':2,'method':'tools/call','params':{'name':'service-restart','arguments':{}}})
        self.assertTrue(response['result']['isError'])
    def test_stale_operation_is_unknown(self):
        self.login()
        state.write('operation.json',{'id':'a','stage':'connecting','updated':int(time.time())-200})
        self.assertEqual(self.client.get('/api/operation').json['data']['stage'],'unknown')

if __name__=='__main__':unittest.main()
