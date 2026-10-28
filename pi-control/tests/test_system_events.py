import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import app
import observer
from system_events import EventStore, SystemMonitor, bounded_command, classify, clean


def entry(message, cursor='cursor-1', timestamp=1000, **fields):
    result=dict(MESSAGE=message,__CURSOR=cursor,__REALTIME_TIMESTAMP=str(int(timestamp*1000000)),
                _BOOT_ID='boot-a',_TRANSPORT='kernel')
    result.update(fields)
    return result


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'system-events.json'
        self.now=1000
        self.store=EventStore(self.path,clock=lambda:self.now)

    def test_recognizes_real_usb_ntfs_and_fat_failure_without_claiming_hardware_death(self):
        cases=[('usb 1-1.1: USB disconnect, device number 5','usb','warning'),
               ('Buffer I/O error on dev sda1, logical block 19068, lost sync page write','storage','error'),
               ('ntfs3(sda1): Mark volume as dirty due to NTFS errors','storage','error'),
               ('ntfs3(sda1): It is recommened to use chkdsk.','storage','error'),
               ('FAT-fs (sda2): Volume was not properly unmounted. Some data may be corrupt. Please run fsck.','storage','error')]
        for text,kind,level in cases:
            result=classify(entry(text))
            self.assertEqual((result['kind'],result['level']),(kind,level))
            self.assertNotIn('hỏng vật lý',result['message'])
        self.assertIsNone(classify(entry('arbitrary sensitive kernel debug')))

    def test_arbitrary_application_logs_not_exposed_and_credentials_redacted(self):
        arbitrary=entry('password=very secret',_SYSTEMD_UNIT='other.service')
        arbitrary['_TRANSPORT']='stdout'
        self.assertIsNone(classify(arbitrary))
        for value in ['error token=SECRET abc','error "password": "SPACE SECRET"','Bearer SECRET','failed https://user:pass@host/?token=SECRET']:
            self.assertNotIn('SECRET',clean(value))
        self.assertIsNone(classify(entry(['binary'])))
        invalid=entry('USB disconnect');invalid['__REALTIME_TIMESTAMP']='nan'
        self.assertIsNone(classify(invalid))

    def test_systemd_identifier_cannot_spoof_manager(self):
        value=entry('piwifi-web.service: Failed with result exit-code',SYSLOG_IDENTIFIER='systemd')
        value['_TRANSPORT']='syslog'
        self.assertIsNone(classify(value))
        value.update(_PID='1',_UID='0')
        self.assertEqual(classify(value)['kind'],'service')
        value['MESSAGE']='piwifi-guard.service: Deactivated successfully.'
        self.assertIsNone(classify(value),'Normal oneshot completion is not a failure')

    def test_dedup_grouping_exact_replay_and_restart_checkpoint(self):
        rows=[entry('Buffer I/O error on dev sda1, block 1','a',999),entry('Buffer I/O error on dev sda1, block 2','b',1000)]
        self.store.ingest(rows);self.store.ingest(rows)
        self.assertEqual(len(self.store.items),1);self.assertEqual(self.store.items[0]['count'],2)
        self.assertFalse(self.path.exists())
        self.now=1060;self.assertTrue(self.store.flush())
        saved=EventStore(self.path,clock=lambda:self.now)
        saved.ingest(rows)
        self.assertEqual(saved.items[0]['count'],2)
        self.assertEqual(saved.cursor,'b')
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        # Different disk or boot is a different group.
        saved.ingest([entry('Buffer I/O error on dev sda2, block 2','c',1000)])
        other=entry('Buffer I/O error on dev sda1, block 3','d',1000);other['_BOOT_ID']='boot-b'
        saved.ingest([other]);self.assertEqual(len(saved.items),3)

    def test_polling_and_idle_flush_do_not_write(self):
        self.store.add('storage','SSD chỉ đọc')
        self.store.flush(force=True)
        before=(self.path.read_bytes(),self.path.stat().st_mtime_ns)
        for i in range(10):
            self.now+=60;self.store.snapshot();self.assertFalse(self.store.flush())
        self.assertEqual((self.path.read_bytes(),self.path.stat().st_mtime_ns),before)
        self.store.ingest([entry('uninteresting kernel line','idle-cursor',self.now)])
        self.assertFalse(self.store.flush())
        self.assertEqual(self.path.stat().st_mtime_ns,before[1])

    def test_reverse_journal_batch_groups_and_checkpoints_newest_cursor(self):
        rows=[entry(f'Buffer I/O error on dev sda1, block {i}',str(i),998+i) for i in range(3)]
        ignored=entry('uninteresting kernel line','newest',1001)
        self.store.ingest([ignored,*reversed(rows)])
        self.assertEqual(len(self.store.items),1)
        row=self.store.items[0]
        self.assertEqual((row['first_timestamp'],row['timestamp'],row['count']),(998,1000,3))
        self.assertIn('block 2',row['detail'])
        self.assertEqual(self.store.cursor,'newest')
        self.store.ingest(list(reversed(rows)))
        self.assertEqual(row['count'],3)
        self.assertEqual(self.store.cursor,'newest','Replaying older events must not regress the cursor')

    def test_late_event_keeps_latest_detail_and_separate_failure_episodes(self):
        self.store.ingest([entry('Buffer I/O error on dev sda1, block 2','new',1000)])
        self.store.ingest([entry('Buffer I/O error on dev sda1, block 1','old',999)])
        row=self.store.items[0]
        self.assertEqual((row['first_timestamp'],row['timestamp'],row['count']),(999,1000,2))
        self.assertIn('block 2',row['detail'])
        self.now=1401
        self.store.ingest([entry('Buffer I/O error on dev sda1, block 3','later',1401)])
        self.assertEqual(len(self.store.items),2)

    def test_tunnel_noise_suppressed_but_distinct_failures_and_other_services_remain(self):
        def service(text,unit='cloudflared.service'):
            return entry(text,_TRANSPORT='stdout',_SYSTEMD_UNIT=unit)
        cancel='ERR Request failed error="Incoming request ended abruptly: context canceled"'
        self.assertIsNone(classify(service(cancel)))
        self.assertIsNotNone(classify(service(cancel,'piwifi-web.service')))
        dns=classify(service('ERR error="lookup region1.v2.argotunnel.com: i/o timeout"'))
        origin=classify(service('ERR error="Unable to reach the origin service: connection refused"'))
        quic=classify(service('ERR error="failed to dial to edge with quic: timeout: no recent network activity"'))
        datagram=classify(service('ERR error="datagram manager error: timeout: no recent network activity"'))
        self.assertNotEqual(dns['group'],origin['group'])
        self.assertEqual(quic['group'],datagram['group'])
        self.assertIn('DNS',dns['message'])
        self.assertIn('Dashboard',origin['message'])

    def test_user_services_are_not_grouped_under_shared_user_manager(self):
        def user(unit):return entry('Error: device missing',_TRANSPORT='stdout',_SYSTEMD_UNIT='user@1000.service',_SYSTEMD_USER_UNIT=unit)
        media=classify(user('pi-media.service'));browser=classify(user('pi-media-browser.service'))
        self.assertEqual(media['source'],'pi-media.service')
        self.assertNotEqual(media['group'],browser['group'])

    def test_migrate_old_reverse_rows_once_preserving_counts_and_replay_ids(self):
        rows=[]
        for i,count in [(2,3),(1,2),(0,1)]:
            rows.append(dict(id=str(i),timestamp=998+i,first_timestamp=998+i,kind='storage',level='error',
                             message='Ổ lưu phát sinh lỗi đọc/ghi',detail=f'Buffer I/O error on dev sda1, block {i}',
                             count=count,group='storage:Ổ lưu phát sinh lỗi đọc/ghi:sda1',origin='journal',boot='boot-a'))
        self.path.write_text(json.dumps(dict(version=1,items=rows,seen=['0','1','2'],cursor='last',boot='boot-a')))
        before=self.path.read_bytes()
        restored=EventStore(self.path,clock=lambda:self.now)
        self.assertEqual(self.path.read_bytes(),before,'Loading/migration must not write until checkpoint')
        self.assertTrue(restored.dirty)
        self.assertEqual(len(restored.items),1)
        self.assertEqual(restored.items[0]['count'],6)
        self.assertEqual((restored.items[0]['first_timestamp'],restored.items[0]['timestamp']),(998,1000))
        self.assertIn('block 2',restored.items[0]['detail'])
        self.assertEqual(restored.cursor,'last')
        restored.add('storage','ignored replay',ident='1');self.assertEqual(len(restored.items),1)
        self.assertTrue(restored.flush(force=True))
        stamp=self.path.stat().st_mtime_ns
        again=EventStore(self.path,clock=lambda:self.now)
        self.assertFalse(again.dirty);self.assertFalse(again.flush(force=True))
        self.assertEqual(again.items,restored.items)
        self.assertEqual(self.path.stat().st_mtime_ns,stamp)

    def test_old_tunnel_history_compacts_by_failure_type_and_preserves_outage_gap(self):
        from system_events import compact_events
        def row(timestamp,detail):
            return dict(id=str(timestamp),timestamp=timestamp,count=2,kind='service',level='error',origin='journal',
                        boot='a',message='Dịch vụ ghi nhận lỗi',group='service:Dịch vụ ghi nhận lỗi:cloudflared.service',detail=detail)
        rows=[row(800,'error="lookup region1: i/o timeout"'),row(801,'error="lookup region1: i/o timeout"'),
              row(802,'error="Unable to reach the origin service: connection refused"'),
              row(803,'error="Incoming request ended abruptly: context canceled"'),row(1102,'error="lookup region1: i/o timeout"')]
        result=compact_events(list(reversed(rows)))
        self.assertEqual(len(result),3)
        self.assertEqual(sum(r['count'] for r in result),8)
        self.assertEqual(sorted(r['count'] for r in result),[2,2,4])

    def test_failed_write_keeps_ram_and_retries_with_backoff(self):
        self.store.add('storage','Disk error','error')
        with patch('system_events.os.replace',side_effect=OSError('disk full')) as replace:
            self.assertFalse(self.store.flush(force=True))
            self.assertFalse(self.store.flush(force=True));self.assertEqual(replace.call_count,1)
        self.assertTrue(self.store.dirty);self.assertIn('RAM',self.store.snapshot()['meta']['error'])
        self.now+=60;self.assertTrue(self.store.flush());self.assertFalse(self.store.dirty)

    def test_retention_cap_invalid_old_snapshot_and_symlink_refusal(self):
        for i in range(2010):
            self.store.add('system',f'event-{i}',timestamp=1000,ident=str(i))
        self.assertEqual(len(self.store.items),2000)
        self.assertEqual(len(self.store.snapshot()['events']),400)
        self.now+=31*86400;self.assertEqual(self.store.snapshot()['events'],[])
        self.store.prune();self.assertEqual(self.store.items,[])
        self.path.write_text('{broken')
        restored=EventStore(self.path,clock=lambda:self.now)
        self.assertTrue(restored.error);self.assertEqual(self.path.read_text(),'{broken')
        self.path.unlink();other=self.path.with_name('private');other.write_text('keep')
        self.path.symlink_to(other)
        restored.add('system','New event');self.assertFalse(restored.flush(force=True))
        self.assertEqual(other.read_text(),'keep')

    def test_bounded_reader_timeout_and_output_limits(self):
        self.assertEqual(bounded_command([sys.executable,'-c','print("ok")']).strip(),'ok')
        with self.assertRaises(ValueError):
            bounded_command([sys.executable,'-c','print("x"*4096)'],limit=512)
        with self.assertRaises(TimeoutError):
            bounded_command([sys.executable,'-c','import time;time.sleep(1)'],timeout=.05)

    def test_mount_transitions_include_read_only_and_do_not_touch_volume(self):
        monitor=SystemMonitor(self.path);monitor.store=self.store
        rw=dict(source='/dev/sda1',fs='ntfs3',readonly=False)
        monitor.observe_mounts({'/mnt/ssd':rw});self.assertEqual(self.store.items,[])
        monitor.observe_mounts({'/mnt/ssd':dict(rw,readonly=True)})
        self.assertEqual(self.store.items[-1]['message'],'Phân vùng đang chỉ đọc')
        monitor.observe_mounts({})
        self.assertEqual(self.store.items[-1]['message'],'Phân vùng không còn được gắn')
        monitor.observe_mounts({'/mnt/ssd':rw})
        self.assertEqual(self.store.items[-1]['message'],'Phân vùng đã được gắn')

    def test_empty_journal_match_is_success_but_stderr_failure_is_not(self):
        command=[sys.executable,'-c','raise SystemExit(1)']
        self.assertEqual(bounded_command(command,empty_ok=True),'')
        with self.assertRaises(OSError):bounded_command(command)
        with self.assertRaises(OSError):
            bounded_command([sys.executable,'-c','import sys;sys.stderr.write("invalid cursor");sys.exit(1)'],empty_ok=True)
        with self.assertRaises(ValueError):
            bounded_command([sys.executable,'-c','import sys;sys.stderr.write("x"*9000)'])

    def test_mount_readonly_uses_host_namespace_not_service_sandbox(self):
        from system_events import mounted_volumes
        def host_mounts(path):
            self.assertEqual(str(path), '/proc/1/mountinfo')
            return '1 0 8:2 / /media/thinh/USB rw,nosuid - vfat /dev/sda2 rw\n2 0 8:1 / /mnt/ssd ro - ntfs3 /dev/sda1 ro\n'
        with patch.object(Path, 'read_text', host_mounts):
            volumes=mounted_volumes()
        self.assertFalse(volumes['/media/thinh/USB']['readonly'])
        self.assertTrue(volumes['/mnt/ssd']['readonly'])

    def test_camera_counts_do_not_log_per_frame_and_old_result_not_reannounced(self):
        monitor=SystemMonitor(self.path);monitor.store=self.store
        state=dict(recording=True,rendering=False,session=dict(id='current',frames=1),last_result=dict(id='old',state='ready'),error='')
        monitor.observe_camera(state)
        for i in range(20):
            state['session']['frames']+=1;monitor.observe_camera(state)
        self.assertEqual(len(self.store.items),1)
        monitor.observe_camera(dict(state,recording=False,rendering=True,session=None,render_session=dict(id='current')))
        monitor.observe_camera(dict(state,recording=False,session=None,last_result=dict(id='current',state='ready',frames=21)))
        self.assertEqual([r['message'] for r in self.store.items],['Đang ghi phiên camera','Phiên camera đã dừng ghi','Camera đang ghép video','Ghép video hoàn tất'])

    def test_journal_unavailable_reports_partial_coverage_and_no_camera_commands(self):
        monitor=SystemMonitor(self.path);monitor.store=self.store
        with patch.object(monitor,'read_journal',side_effect=OSError()),patch('system_events.mounted_volumes',return_value={}),patch('system_events.camera_status',side_effect=OSError()):
            for _ in range(4):monitor.tick()
        self.assertIn('Chưa đọc được log Linux',self.store.snapshot()['meta']['error'])
        self.assertEqual(sum(r['kind']=='camera' for r in self.store.items),1)

    def test_fixed_journal_query_has_selection_cursor_and_limit(self):
        monitor=SystemMonitor(self.path);monitor.store=self.store
        self.store.cursor='saved-cursor'
        raw=json.dumps(entry('usb 1-1.1: USB disconnect, device number 5',timestamp=1000))+'\n'
        with patch('system_events.bounded_command',return_value=raw) as command:
            monitor.read_journal()
        args=command.call_args.args[0]
        self.assertEqual(args[0],'journalctl');self.assertIn('--after-cursor=saved-cursor',args)
        self.assertIn('_TRANSPORT=kernel',args)
        self.assertTrue(any(arg.startswith('--grep=') for arg in args))
        self.assertEqual(self.store.items[0]['kind'],'usb')

    def test_health_and_network_only_log_transitions(self):
        monitor=SystemMonitor(self.path);monitor.store=self.store
        data=dict(temperature=40,power={'undervoltage':False},disks=[],services=[])
        checks=dict(layers=[dict(name='Wi-Fi',state='ok',detail='Saved profile'),dict(name='Địa chỉ IP',state='ok',detail='192.168.1.30')])
        monitor.observe_health(data,checks);monitor.observe_health(data,checks)
        self.assertEqual(self.store.items,[])
        data['power']['undervoltage']=True
        monitor.observe_health(data,checks);monitor.observe_health(data,checks)
        self.assertEqual(len(self.store.items),1)
        checks['layers'][1]['detail']='192.168.2.30'
        monitor.observe_health(data,checks)
        self.assertEqual(self.store.items[-1]['kind'],'network')

    def test_empty_success_without_kernel_access_is_not_reported_as_supported(self):
        monitor=SystemMonitor(self.path)
        with patch('system_events.bounded_command',return_value=''):
            with self.assertRaises(OSError):monitor.read_journal()
        self.assertFalse(monitor.access_checked)

    def test_camera_ipc_contains_only_status_no_viewer_or_mutation(self):
        from system_events import camera_status
        from unittest.mock import MagicMock
        connection=MagicMock()
        connection.makefile.return_value.readline.return_value=b'{"ok":true,"data":{"recording":true}}\n'
        with patch('system_events.socket.socket') as factory:
            factory.return_value.__enter__.return_value=connection
            with patch.dict(os.environ, {'PIWIFI_CAMERA_RUNTIME':'/run/piwifi-camera-runtime'}):
                self.assertTrue(camera_status()['recording'])
        connection.connect.assert_called_once_with('/run/piwifi-camera-runtime/pi-camera.sock')
        connection.sendall.assert_called_once_with(b'{"action":"status"}\n')


class ActivityApiTests(unittest.TestCase):
    def setUp(self):
        self.client=app.app.test_client();app._read_cache.clear()

    def test_auth_default_compatibility_summary_and_read_only_queries(self):
        self.assertEqual(self.client.get('/api/events?summary=1').status_code,302)
        with self.client.session_transaction() as session:session['logged_in']=True
        with patch.object(app,'events',return_value=[dict(timestamp=1,message='legacy')]),patch.object(app,'activity',return_value=dict(events=[],meta={'available':True})) as summary:
            result=self.client.get('/api/events').get_json()
            self.assertIsInstance(result['data'],list)
            for _ in range(3):self.assertTrue(self.client.get('/api/events?summary=1').get_json()['data']['meta']['available'])
            summary.assert_called_once()

    def test_ipc_offline_and_existing_operation_events_are_preserved(self):
        old=dict(timestamp=20,message='Đã triển khai',kind='deploy')
        with patch.object(observer,'ipc_read',return_value=[]),patch.object(observer,'read',return_value=[old]):
            result=observer.activity()
        self.assertEqual(result['events'],[old]);self.assertFalse(result['meta']['available'])


if __name__=='__main__':unittest.main()
