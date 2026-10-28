import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

import runtime_config as runtime
import storage_writes
import audio_client
import audio_agent
import camera_agent
import render_jobs
from deployment_history import Ledger,validate_import,checked_json
from service_catalog import help_rows

HOST=dict(schema=1,desktop_user='thinh',desktop_uid=1000,desktop_home='/home/thinh',generation='a'*32,
          root_uuid='11111111-1111',data_uuid='22222222-2222',data_mount='/srv/pi-control',camera_device='auto')


class RuntimeTests(unittest.TestCase):
    def test_absent_is_legacy(self):
        with tempfile.TemporaryDirectory() as temp:self.assertIsNone(runtime.load(Path(temp)/'absent',False))

    def test_valid_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'runtime.json';path.write_text(json.dumps(HOST));path.chmod(0o644)
            self.assertEqual(runtime.load(path,False),HOST)
            path.chmod(0o666)
            with self.assertRaises(ValueError):runtime.load(path,False)

    def test_reject_unsafe_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'runtime.json'
            for key,value in [('desktop_user','root;echo'),('desktop_uid',True),('desktop_home','/root'),('data_mount','/'),('generation','bad'),('camera_device','/dev/video0')]:
                with self.subTest(key=key):
                    path.write_text(json.dumps(HOST|{key:value}));path.chmod(0o644)
                    with self.assertRaises(ValueError):runtime.load(path,False)

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'link';path.symlink_to('/dev/null')
            with self.assertRaises(ValueError):runtime.load(path,False)

    def test_unit_mapping_and_help(self):
        with patch.object(runtime,'CONFIG',HOST):
            self.assertEqual(runtime.unit('piwifi-web.service'),'pi-control-dashboard.service')
            self.assertEqual(runtime.unit('piwifi-guard.timer'),'pi-control-network-guard.timer')
            rows=help_rows();self.assertTrue(any(r['unit']=='pi-control-audio.service' for r in rows))
            for row in rows:
                for key in ('purpose','stop_impact','normal_inactive','dependencies'):self.assertIn(key,row)

    def test_audio_uses_separate_socket(self):
        response=Mock();response.makefile.return_value=io.BytesIO(b'{"ok":true,"data":{"volume":42}}\n')
        manager=Mock();manager.__enter__=Mock(return_value=response);manager.__exit__=Mock(return_value=False)
        with patch.object(runtime,'CONFIG',HOST),patch.object(audio_client.socket,'socket',return_value=manager):
            self.assertEqual(audio_client.call({'action':'status'}),{'volume':42})
        response.connect.assert_called_once_with('/run/user/1000/pi-audio.sock')

    def test_audio_error_is_not_success(self):
        response=Mock();response.makefile.return_value=io.BytesIO(b'{"ok":false,"error":"offline"}\n')
        manager=Mock();manager.__enter__=Mock(return_value=response);manager.__exit__=Mock(return_value=False)
        with patch.object(runtime,'CONFIG',HOST),patch.object(audio_client.socket,'socket',return_value=manager):
            with self.assertRaisesRegex(ValueError,'offline'):audio_client.call({'action':'status'})

    def test_whole_usb_disk_sampler(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sysroot=root/'sys';procroot=root/'proc'
            disk=sysroot/'devices/usb/block/sda';part=disk/'sda2';part.mkdir(parents=True)
            (part/'partition').write_text('2');(disk/'device').mkdir();(disk/'device/model').write_text('PM991')
            (disk/'stat').write_text('0 0 0 0 0 0 17 0 0 0 0');(sysroot/'dev/block').mkdir(parents=True)
            (sysroot/'dev/block/8:2').symlink_to(part)
            (procroot/'1').mkdir(parents=True);(procroot/'1/mountinfo').write_text('1 2 8:2 / / rw - ext4 /dev/sda2 rw\n')
            (procroot/'sys/kernel/random').mkdir(parents=True);(procroot/'sys/kernel/random/boot_id').write_text('boot')
            (procroot/'uptime').write_text('12.5 10')
            with patch.object(storage_writes,'RUNTIME_CONFIG',HOST):sample=storage_writes.os_disk_sample(sysroot,procroot)
            self.assertEqual((sample['name'],sample['counter'],sample['model']),('sda',17*512,'PM991'))

    def test_camera_only_approved_uuid(self):
        data={'blockdevices':[{'name':'sda','tran':'usb','children':[{'name':'sda2','fstype':'ext4','uuid':'wrong','mountpoints':['/srv/pi-control']},{'name':'sda3','fstype':'ext4','uuid':HOST['data_uuid'],'mountpoints':['/srv/pi-control']}]}]}
        with patch.object(runtime,'CONFIG',HOST),patch.object(camera_agent,'RUNTIME_CONFIG',HOST),patch.object(camera_agent.subprocess,'run',return_value=Mock(stdout=json.dumps(data))):
            self.assertEqual(camera_agent.external_mounts(),[dict(path='/srv/pi-control',uuid=HOST['data_uuid'],fs='ext4')])

    def test_camera_missing_mount_has_no_fallback(self):
        with self.assertRaises(ValueError):camera_agent.storage_target('/srv/pi-control',[])

    def test_help_rendered_with_unique_ids_and_no_commands(self):
        import app
        from html.parser import HTMLParser
        class IDs(HTMLParser):
            def __init__(self):super().__init__();self.ids=[]
            def handle_starttag(self,tag,attrs):self.ids.extend(v for k,v in attrs if k=='id')
        client=app.app.test_client()
        with client.session_transaction() as session:session.update(logged_in=True,csrf='test-help')
        with patch.object(runtime,'CONFIG',HOST),patch.object(app,'helper',return_value={}),patch.object(app,'collect',return_value={}):response=client.get('/')
        self.assertEqual(response.status_code,200);html=response.data.decode();parser=IDs();parser.feed(html)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for row in help_rows():self.assertIn('service-help-'+row['id'],html)
        self.assertIn('pi-control-audio.service',html);self.assertIn('service-help.js',html)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'import.json'
        self.row=dict(event_id='legacy-'+'a'*24,timestamp=100,kind='deploy',message='old deploy',source_generation='legacy-sd',historical_only=True,rollback_available=False)
        self.save(self.row)

    def save(self,row):
        raw=json.dumps(dict(schema='pi-control.deploy-history/v1',source_generation='legacy-sd',event_count=1,events=[row])).encode()
        self.source.write_bytes(raw);self.source.with_suffix('.json.sha256').write_text(hashlib.sha256(raw).hexdigest())

    def test_idempotent_import_and_new_generation(self):
        ledger=Ledger(self.root/'history.json','b'*32)
        self.assertEqual(ledger.import_legacy(self.source),1);before=ledger.path.stat().st_mtime_ns
        self.assertEqual(ledger.import_legacy(self.source),0);self.assertEqual(before,ledger.path.stat().st_mtime_ns)
        ledger.record('dashboard','v1-test','c'*64,'installed');rows=ledger.read()
        self.assertTrue(rows[0]['historical_only']);self.assertFalse(rows[0]['rollback_available'])
        self.assertEqual(rows[1]['source_generation'],'b'*32);self.assertFalse(rows[1]['historical_only'])

    def test_tampered_import(self):
        self.source.write_text('{}')
        with self.assertRaises(ValueError):validate_import(self.source)

    def test_invalid_flags(self):
        self.save(self.row|{'rollback_available':True})
        with self.assertRaises(ValueError):validate_import(self.source)

    def test_fifo_refused_without_blocking(self):
        path=self.root/'fifo';os.mkfifo(path)
        with self.assertRaises(ValueError):checked_json(path)

    def test_symlink_refused(self):
        path=self.root/'link';path.symlink_to(self.source)
        with self.assertRaises(OSError):checked_json(path)


class RenderJobTests(unittest.TestCase):
    def test_agent_restart_reconnects_to_existing_worker(self):
        session=dict(id='20261027T120000-1234abcd',mode='interval',frames=2,bytes=100,started=1,target=dict(mount='/srv/pi-control'))
        with tempfile.TemporaryDirectory() as temp,patch.object(runtime,'CONFIG',HOST),patch.object(camera_agent,'RUNTIME_CONFIG',HOST),patch.object(camera_agent,'STATE',Path(temp)),patch.object(render_jobs,'pending',return_value=session),patch.object(camera_agent.threading,'Thread') as thread:
            camera=camera_agent.Camera()
            self.assertTrue(camera.rendering);self.assertEqual(camera.render_session,session)
            thread.assert_called_once_with(target=camera.recover_render,args=(session,),daemon=True)
            thread.return_value.start.assert_called_once()

    def test_ids_cannot_be_commands_or_paths(self):
        for value in ('../bad','x;reboot','20261027T120000-bad',None):
            with self.subTest(value=value),self.assertRaises(ValueError):render_jobs.job_path(value)

    def test_completed_result(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(render_jobs,'directory',return_value=Path(temp)):
            ident='20261027T120000-1234abcd';result=dict(id=ident,state='ready',frames=2)
            render_jobs.write_private(render_jobs.job_path(ident,True),result)
            self.assertEqual(render_jobs.wait(ident),result)

    def test_active_job_rejects_resubmit(self):
        with patch.object(render_jobs,'active',return_value=True):
            with self.assertRaises(ValueError):render_jobs.submit({'id':'20261027T120000-1234abcd'})

    def test_lost_worker_stops_wait(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(render_jobs,'directory',return_value=Path(temp)),patch.object(render_jobs,'active',return_value=False),patch.object(render_jobs.time,'monotonic',side_effect=[0,11,11]):
            with self.assertRaisesRegex(ValueError,'Worker'):render_jobs.wait('20261027T120000-1234abcd')

    def test_unsafe_session_path(self):
        ident='20261027T120000-1234abcd'
        with patch.object(render_jobs,'CONFIG',HOST),patch.object(render_jobs,'read_private',return_value=dict(schema=1,session=dict(id=ident,target={},folder='/etc'))):
            with self.assertRaisesRegex(ValueError,'storage'):render_jobs.validated_session(ident)
