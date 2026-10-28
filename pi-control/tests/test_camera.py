import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
from PIL import Image
import camera_agent as agent
from camera_policy import PositionGate, ViewerPower, regions
import app


def jpeg():
    image = Image.new('RGB',(128,72))
    image.putdata([((x*19)%256,(x*37)%256,(x*73)%256) for x in range(128*72)])
    result = io.BytesIO()
    image.save(result,format='JPEG')
    return result.getvalue()


class PositionTests(unittest.TestCase):
    def test_requires_departure_then_stable_return(self):
        gate=PositionGate()
        self.assertFalse(gate.feed([0,0],0))
        self.assertFalse(gate.feed([0,0],2))
        self.assertFalse(gate.feed([.2,.2],3))
        self.assertFalse(gate.feed([.2,.2],3.5))
        self.assertFalse(gate.feed([0,0],4))
        self.assertTrue(gate.feed([0,0],4.7))
        self.assertFalse(gate.feed([0,0],8))

    def test_both_regions_required_and_noise_does_not_rearm(self):
        gate=PositionGate()
        gate.feed([.2,.2],0);gate.feed([.2,.2],1)
        self.assertFalse(gate.feed([0,.2],2))
        gate.feed([0,0],3)
        self.assertTrue(gate.feed([0,0],4))
        gate.feed([.07,.07],5);gate.feed([0,0],6)
        self.assertFalse(gate.feed([0,0],8))

    def test_bad_samples_reset_settle(self):
        gate=PositionGate()
        gate.feed([.2,.2],0);gate.feed([.2,.2],1);gate.feed([0,0],2)
        self.assertFalse(gate.feed([float('nan'),0],3))
        self.assertFalse(gate.feed([0,0],4))
        self.assertTrue(gate.feed([0,0],5))

    def test_wide_threshold_never_arms_and_diagnostics_explain_why(self):
        gate=PositionGate(threshold=.15,settle=.2)
        for i in range(100):
            self.assertFalse(gate.feed([.116,.108] if i%2 else [.009,.006],i*.25))
        data=gate.diagnostics(25)
        self.assertEqual(data['phase'],'waiting_departure');self.assertFalse(data['armed'])
        self.assertEqual(data['departure_threshold'],22.5)
        self.assertEqual(data['recent_max'],[11.6,10.8])
        # A lower configured threshold recognizes the same departure/return.
        gate=PositionGate(threshold=.06,settle=.2)
        gate.feed([.116,.108],0);gate.feed([.116,.108],.5);gate.feed([.009,.006],1)
        self.assertTrue(gate.feed([.009,.006],1.3))

    def test_diagnostics_are_bounded_and_do_not_change_gate_decisions(self):
        observed,plain=PositionGate(settle=.2),PositionGate(settle=.2)
        for i in range(1000):
            now=i*.1;scores=[.2,.2] if i%20<10 else [0,0]
            self.assertEqual(observed.feed(scores,now),plain.feed(scores,now))
            observed.diagnostics(now);observed.diagnostics(now)
        self.assertLessEqual(len(observed.samples),360)
        self.assertLessEqual(observed.diagnostics(100)['samples'],301)
        self.assertIsNone(observed.diagnostics(200)['recent_max'])
        observed.feed([float('nan'),0],201)
        self.assertEqual(observed.diagnostics(201)['phase'],'invalid_frame')

    def test_diagnostics_follow_departure_return_and_capture(self):
        gate=PositionGate(settle=.2)
        for scores,now,phase in [([.2,.2],0,'leaving'),([.2,.2],.5,'waiting_return'),
                                 ([0,0],1,'settling'),([0,0],1.3,'captured'),([0,0],2,'waiting_departure')]:
            gate.feed(scores,now)
            self.assertEqual(gate.diagnostics(now)['phase'],phase)

    def test_regions_reject_tiny_or_out_of_bounds(self):
        for value in (None,[],[[0,0,.01,.01]]*2,[[.9,.9,.2,.2]]*2,[[0,0,True,.4]]*2):
            with self.assertRaises(ValueError):regions(value)

    def test_regions_cannot_be_duplicates(self):
        with self.assertRaises(ValueError):regions([[.1,.1,.2,.2],[.1,.1,.2,.2]])


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name,value in [('STATE',self.root/'state'),('RUNTIME',self.root),('TRIAL',self.root/'trial')]:
            p=patch.object(agent,name,value);p.start();self.addCleanup(p.stop)
        self.camera=agent.Camera()
        self.frame=jpeg()
        self.camera.frame=self.frame;self.camera.frame_at=time.monotonic()

    def start(self,**kwargs):
        with patch.object(agent,'check_target'):
            self.camera.start(dict(mode='interval',storage='ram',interval=2,**kwargs))

    def test_unknown_storage_never_falls_back_to_sd(self):
        with self.assertRaises(ValueError):agent.storage_target('/tmp/unsafe',mounts=[])
        self.assertFalse((self.root/'trial').exists())

    def test_storage_preference_follows_uuid_after_restart_and_remount(self):
        target=dict(root=str(self.root), mount='/media/old', device=1, uuid='SSD-123', trial=False)
        with patch.object(agent,'storage_target',return_value=target),patch.object(agent,'check_target'):
            self.camera.set_storage('/media/old')
        saved=agent.STATE/'storage.json'
        before=saved.stat().st_mtime_ns
        restored=agent.Camera()
        restored.mounts=[dict(path='/mnt/new',uuid='SSD-123',fs='ntfs')]
        restored.mounts_at=time.monotonic()
        self.assertEqual(restored.status()['storage_default'],'/mnt/new')
        restored.status();restored.status()
        self.assertEqual(saved.stat().st_mtime_ns,before)
        self.assertEqual(saved.stat().st_mode & 0o777,0o600)

    def test_missing_preferred_ssd_never_defaults_to_ram_or_another_disk(self):
        self.camera.storage_uuid='MISSING-123'
        with patch.object(agent,'external_mounts',return_value=[dict(path='/media/other',uuid='OTHER',fs='ntfs')]):
            with self.assertRaises(ValueError):
                self.camera.start(dict(mode='interval',interval=2))
        self.assertIsNone(self.camera.default_storage())
        self.assertFalse(agent.TRIAL.exists())
        self.assertIsNone(self.camera.session)

    def test_storage_choice_is_explicit_and_locked_during_recording(self):
        self.camera.storage_uuid='OLD'
        with patch.object(agent,'check_target'):
            self.camera.set_storage('ram')
        self.assertEqual(agent.Camera().storage_uuid,'')
        self.start()
        with self.assertRaises(ValueError):self.camera.set_storage('ram')

    def test_session_photos_use_actual_sorted_files_and_read_without_writes(self):
        self.start();session=self.camera.session;self.camera.session=None
        folder=Path(session['folder'])
        (folder/'frame-000007.jpg').write_bytes(self.frame)
        (folder/'frame-000000.jpg').write_bytes(self.frame)
        (folder/'frame-020000.jpg').write_bytes(self.frame)
        (folder/'frame-000003.jpg').symlink_to(folder/'frame-000000.jpg')
        before=(folder/'session.json').stat().st_mtime_ns
        payload=dict(id=session['id'],storage='ram')
        result=self.camera.dispatch(dict(action='photos',**payload))
        self.assertEqual(result,dict(indices=[0,7],total=2))
        import base64
        photo=self.camera.dispatch(dict(action='photo',index=7,**payload))
        self.assertEqual(base64.b64decode(photo['jpeg']),self.frame)
        self.assertEqual((folder/'session.json').stat().st_mtime_ns,before)
        self.assertFalse(self.camera.process)

    def test_photo_rejects_links_missing_files_and_invalid_jpeg(self):
        self.start();session=self.camera.session;self.camera.session=None
        folder=Path(session['folder']);payload=dict(action='photo',id=session['id'],storage='ram',index=0)
        with self.assertRaises(OSError):self.camera.dispatch(payload)
        (folder/'frame-000000.jpg').symlink_to(folder/'session.json')
        with self.assertRaises(OSError):self.camera.dispatch(payload)
        (folder/'frame-000000.jpg').unlink();(folder/'frame-000000.jpg').write_bytes(b'not a jpeg')
        with self.assertRaises(ValueError):self.camera.dispatch(payload)
        (folder/'frame-000000.jpg').write_bytes(b'\xff\xd8'+b'x'*agent.MAX_FRAME+b'\xff\xd9')
        with self.assertRaises(ValueError):self.camera.dispatch(payload)
        (folder/'session.json').unlink();(folder/'session.json').symlink_to(folder/'frame-000000.jpg')
        with self.assertRaises(OSError):self.camera.dispatch(dict(payload,action='photos'))

    def test_photo_paths_are_bounded_and_missing_storage_is_not_created(self):
        ident='20261024T140545-e84c6aa5'
        for index in (-1,20000,True,'0'):
            with self.assertRaises(ValueError):self.camera.dispatch(dict(action='photo',id=ident,storage='ram',index=index))
        with self.assertRaises(ValueError):self.camera.dispatch(dict(action='photos',id='../escape',storage='ram'))
        with self.assertRaises(OSError):self.camera.dispatch(dict(action='photos',id=ident,storage='ram'))
        self.assertFalse(agent.TRIAL.exists())
        with patch.object(agent,'external_mounts',return_value=[]):
            with self.assertRaises(ValueError):self.camera.dispatch(dict(action='photos',id=ident,storage='/mnt/missing'))
        self.assertFalse(agent.TRIAL.exists())

    def test_photo_rejects_session_directory_link_and_bad_manifest(self):
        self.start();session=self.camera.session;self.camera.session=None
        folder=Path(session['folder']);payload=dict(action='photos',id=session['id'],storage='ram')
        for data in ('[]','{}','not json'):
            (folder/'session.json').write_text(data)
            with self.assertRaises(ValueError):self.camera.dispatch(payload)
        renamed=folder.with_name('elsewhere');folder.rename(renamed);folder.symlink_to(renamed,target_is_directory=True)
        with self.assertRaises(OSError):self.camera.dispatch(payload)

    def test_removed_device_prevents_writes(self):
        self.start();self.camera.session['target']['device']=-1
        with patch.object(self.camera,'stop') as stop:
            self.camera.tick(self.frame,time.monotonic())
            stop.assert_called_once()
        self.assertFalse(list((self.root/'trial').glob('*/frame-*.jpg')))

    def test_interval_records_once_until_deadline(self):
        self.start()
        now=time.monotonic()
        with patch.object(agent,'check_target'):
            self.camera.tick(self.frame,now);self.camera.tick(self.frame,now+.5)
            self.camera.tick(self.frame,now+2.1)
        self.assertEqual(self.camera.session['frames'],2)
        self.assertEqual(len(list((self.root/'trial').glob('*/frame-*.jpg'))),2)

    def test_library_uses_live_counters_without_manifest_writes(self):
        self.start();session=self.camera.session
        manifest=Path(session['folder'])/'session.json'
        before=(manifest.read_bytes(),manifest.stat().st_mtime_ns)
        with patch.object(agent,'check_target'):
            self.camera.tick(self.frame,time.monotonic())
        for _ in range(2):
            row=self.camera.recordings()[0]
            self.assertEqual((row['state'],row['frames'],row['bytes']),('recording',1,len(self.frame)))
            summary=self.camera.status()['session']
            self.assertEqual(summary['storage'],'ram')
            self.assertNotIn('folder',summary);self.assertNotIn('target',summary);self.assertNotIn('gate',summary)
        self.assertEqual((manifest.read_bytes(),manifest.stat().st_mtime_ns),before)

    def test_library_marks_abandoned_manifest_as_interrupted_not_zero(self):
        self.start();session=self.camera.session
        # Even a matching ID must not overlay a different directory.
        session['folder']=str(self.root/'elsewhere'/session['id'])
        row=self.camera.recordings()[0]
        self.assertEqual(row['state'],'interrupted');self.assertIsNone(row['frames'])
        self.camera.session=None
        row=agent.Camera().recordings()[0]
        self.assertEqual(row['state'],'interrupted');self.assertIsNone(row['frames'])

    def test_library_tracks_rendering_then_final_result(self):
        self.start();session=self.camera.session
        with patch.object(agent,'check_target'):
            self.camera.tick(self.frame,time.monotonic())
        with patch.object(agent.threading,'Thread') as worker:
            self.camera.stop()
            worker.return_value.start.assert_called_once()
        self.assertEqual(self.camera.recordings()[0]['state'],'rendering')
        self.assertEqual(self.camera.status()['render_session']['frames'],1)
        with patch.object(agent,'check_target'):
            self.camera.render(session)
        row=self.camera.recordings()[0]
        self.assertEqual((row['state'],row['frames']),('incomplete',1))
        self.assertFalse(self.camera.rendering);self.assertIsNone(self.camera.render_session)
        self.assertEqual(self.camera.last_result['storage'],'ram')

    def test_corrupt_interval_frame_is_skipped_and_next_valid_frame_records(self):
        self.start();session=self.camera.session;now=time.monotonic()
        with patch.object(agent,'check_target'):
            self.camera.tick(b'\xff\xd8broken\xff\xd9',now)
            self.assertIs(self.camera.session,session)
            self.assertEqual(session['frames'],0)
            self.camera.tick(self.frame,now+.2)
        self.assertEqual(session['frames'],1)
        self.assertEqual(self.camera.dropped_frames,1)
        self.assertEqual(self.camera.error,'')
        self.assertEqual((Path(session['folder'])/'frame-000000.jpg').read_bytes(),self.frame)

    def test_position_decoder_error_keeps_session_and_resets_stability(self):
        rois=[[.05,.05,.3,.3],[.5,.5,.3,.3]]
        self.camera.config=dict(regions=rois);self.camera.references=agent.fingerprints(self.frame,rois)
        with patch.object(agent,'check_target'):
            self.camera.start(dict(mode='position',storage='ram',interval=2))
        session=self.camera.session
        with patch.object(agent,'fingerprints',side_effect=OSError('broken data stream when reading image file')):
            self.camera.tick(self.frame,time.monotonic())
        self.assertIs(self.camera.session,session)
        self.assertFalse(self.camera.rendering)
        self.assertEqual(self.camera.dropped_frames,1)
        self.camera.tick(self.frame,time.monotonic()+1)
        self.assertIs(self.camera.session,session)
        self.assertEqual(self.camera.error,'')

    def test_corrupt_calibration_is_retryable_and_does_not_replace_reference(self):
        self.camera.frozen=b'\xff\xd8broken\xff\xd9';self.camera.frozen_at=time.monotonic()
        with self.assertRaisesRegex(ValueError,'Ảnh mẫu bị lỗi'):
            self.camera.calibrate(dict(regions=[[.05,.05,.3,.3],[.5,.5,.3,.3]],threshold=6))
        self.assertFalse((agent.STATE/'reference.jpg').exists())

    def test_trial_time_and_size_limits(self):
        self.start()
        with patch.object(self.camera,'stop') as stop:
            self.camera.tick(self.frame,self.camera.session['monotonic']+601)
            stop.assert_called_once()
        self.camera.session['bytes']=64*1024**2
        with patch.object(agent,'check_target'),patch.object(self.camera,'stop') as stop:
            self.camera.tick(self.frame,time.monotonic())
            stop.assert_called_once()

    def test_position_cannot_start_without_calibration(self):
        with self.assertRaises(ValueError):self.camera.start(dict(mode='position'))

    def test_position_status_explains_wait_and_warns_wide_roi_without_writes(self):
        rois=[[.01,.01,.2,.2],[.3,.3,.65,.65]]
        self.camera.config=dict(regions=rois,threshold=.15,settle=.2)
        self.camera.references=agent.fingerprints(self.frame,rois)
        with patch.object(agent,'check_target'):
            self.camera.start(dict(mode='position',storage='ram'))
        manifest=Path(self.camera.session['folder'])/'session.json'
        before=(manifest.read_bytes(),manifest.stat().st_mtime_ns)
        self.camera.tick(self.frame,time.monotonic())
        status=self.camera.status()
        self.assertEqual(status['tracking']['phase'],'waiting_departure')
        self.assertEqual(status['tracking']['departure_threshold'],22.5)
        self.assertIn('Chờ rời',status['session']['note'])
        self.assertIn('quá rộng',status['calibration_warning'])
        self.assertEqual((manifest.read_bytes(),manifest.stat().st_mtime_ns),before)

    def test_calibration_requires_frozen_frame_and_persists_only_on_explicit_action(self):
        payload=dict(regions=[[.05,.05,.3,.3],[.5,.5,.3,.3]],threshold=6)
        with self.assertRaises(ValueError):self.camera.calibrate(payload)
        self.camera.dispatch(dict(action='freeze'));self.camera.calibrate(payload)
        self.assertTrue((agent.STATE/'reference.jpg').exists())
        self.assertTrue(agent.Camera().references)
        before=(agent.STATE/'calibration.json').stat().st_mtime_ns
        self.camera.status();self.camera.status()
        self.assertEqual(before,(agent.STATE/'calibration.json').stat().st_mtime_ns)

    def test_frame_requires_freshness(self):
        self.camera.frame_at-=10
        with self.assertRaises(ValueError):self.camera.fresh_frame()

    def test_position_rejects_flat_reference(self):
        image=Image.new('RGB',(128,72),'gray');stream=io.BytesIO();image.save(stream,format='JPEG')
        self.camera.frozen=stream.getvalue();self.camera.frozen_at=time.monotonic()
        with self.assertRaises(ValueError):self.camera.calibrate(dict(regions=[[0,0,.4,.4],[.5,.5,.4,.4]]))

    def test_session_path_traversal_rejected(self):
        with self.assertRaises(ValueError):self.camera.recording_path('../../etc','ram')

    def test_delete_refuses_foreign_files_and_symlinks(self):
        self.start();session=self.camera.session;self.camera.session=None
        folder=Path(session['folder']);(folder/'foreign.txt').write_text('keep')
        self.camera.mounts_at=time.monotonic()
        with self.assertRaises(ValueError):self.camera.dispatch(dict(action='delete',id=session['id'],storage='ram'))
        self.assertTrue((folder/'foreign.txt').exists())

    def test_stopped_session_renders_real_mp4(self):
        self.start();now=time.monotonic()
        with patch.object(agent,'check_target'):
            self.camera.tick(self.frame,now);self.camera.tick(self.frame,now+2.1)
            session=self.camera.session;self.camera.session=None
            self.camera.render(session)
        self.assertEqual(self.camera.last_result['state'],'ready')
        result=Path(session['folder'])/'timelapse.mp4'
        self.assertGreater(result.stat().st_size,100)
        self.assertEqual(result.read_bytes()[4:8],b'ftyp')

    def test_manual_off_cannot_interrupt_recording(self):
        self.start()
        with patch.object(self.camera,'disable') as disable:
            with self.assertRaises(ValueError):self.camera.dispatch(dict(action='power',enabled=False))
            disable.assert_not_called()

    def test_intentional_idle_close_is_not_reported_as_camera_timeout(self):
        process=Mock();process.poll.return_value=None
        self.camera.process=process;self.camera.opened_at=time.monotonic()-30
        self.camera.disable()
        self.assertTrue(self.camera.closing)
        self.assertEqual(self.camera.frame_at,0)
        self.camera.check_stream()
        self.assertEqual(self.camera.error,'')
        process.terminate.assert_called_once()

    def test_real_camera_timeout_still_stops_recording_once(self):
        self.start();process=Mock();process.poll.return_value=None
        self.camera.process=process;self.camera.opened_at=time.monotonic()-30;self.camera.frame_at=0
        with patch.object(self.camera,'stop') as stop:
            self.camera.check_stream();self.camera.check_stream()
            stop.assert_called_once()
        process.terminate.assert_called_once()
        self.assertIn('8 giây',self.camera.error)

    def test_viewer_lease_starts_and_idle_stops_camera(self):
        self.camera.mounts_at=time.monotonic()
        with patch.object(self.camera,'enable') as enable:
            self.camera.dispatch(dict(action='watch',viewer='a'*64,watching=True))
            enable.assert_called_once()
        self.camera.process=Mock();self.camera.process.poll.return_value=None
        self.camera.power_policy.viewers.clear()
        self.camera.power_policy.idle_since=time.monotonic()-6
        with patch.object(self.camera,'disable') as disable:
            self.camera.power_tick();disable.assert_called_once()

    def test_power_settings_write_only_on_explicit_toggle(self):
        with patch.object(self.camera,'enable'):
            self.camera.set_automatic(False)
        before=(agent.STATE/'power.json').stat().st_mtime_ns
        self.camera.power_tick();self.camera.status()
        self.assertEqual(before,(agent.STATE/'power.json').stat().st_mtime_ns)
        self.assertFalse(agent.Camera().power_policy.automatic)


class ViewerPowerTests(unittest.TestCase):
    def test_two_viewers_and_last_leave_grace(self):
        policy=ViewerPower()
        policy.watch('a'*64,True,0);policy.watch('b'*64,True,0)
        self.assertTrue(policy.decision(False,1))
        policy.watch('a'*64,False,2)
        self.assertTrue(policy.decision(False,3))
        policy.watch('b'*64,False,4)
        self.assertIsNone(policy.decision(False,4))
        self.assertIsNone(policy.decision(False,8))
        self.assertFalse(policy.decision(False,9))

    def test_crashed_browser_expires_without_release(self):
        policy=ViewerPower();policy.watch('a'*64,True,0)
        self.assertTrue(policy.decision(False,14))
        self.assertIsNone(policy.decision(False,15))
        self.assertFalse(policy.decision(False,20))

    def test_recording_stays_on_without_viewers_then_rests(self):
        policy=ViewerPower()
        self.assertTrue(policy.decision(True,200))
        self.assertIsNone(policy.decision(False,201))
        self.assertFalse(policy.decision(False,206))

    def test_manual_off_respected_until_new_visit(self):
        policy=ViewerPower();policy.watch('a'*64,True,0);policy.manual(False)
        policy.watch('a'*64,True,1)
        self.assertIsNone(policy.decision(False,1))
        self.assertFalse(policy.decision(False,6))
        policy.watch('a'*64,False,7);policy.watch('b'*64,True,8)
        self.assertTrue(policy.decision(False,8))

    def test_manual_mode_does_not_auto_open_or_close(self):
        policy=ViewerPower(False);policy.watch('a'*64,True,0)
        self.assertIsNone(policy.decision(False,1))
        self.assertIsNone(policy.decision(False,200))

    def test_bad_ids_and_viewer_limit(self):
        policy=ViewerPower()
        with self.assertRaises(ValueError):policy.watch('wrong',True,0)
        with self.assertRaises(ValueError):policy.watch('a'*64,1,0)
        for i in range(32):policy.watch(f'{i:064x}',True,0)
        with self.assertRaises(ValueError):policy.watch('f'*64,True,1)
        policy.watch('f'*64,True,16)


class CameraAPITests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING']=True
        self.client=app.app.test_client()

    def authenticate(self):
        with self.client.session_transaction() as session:
            session['logged_in']=True;session['csrf']='test-token'

    def test_private_endpoints_require_login(self):
        for path in ('/api/camera','/api/camera/frame','/api/camera/video/test','/api/camera/photos/test','/api/camera/photo/test/0'):
            self.assertEqual(self.client.get(path).status_code,302)

    def test_csrf_and_action_allowlist(self):
        self.authenticate()
        with patch.object(app.camera,'call') as call:
            self.assertEqual(self.client.post('/api/camera',json=dict(action='power',enabled=True)).status_code,403)
            self.assertEqual(self.client.post('/api/camera',json=dict(action='download'),headers={'X-CSRF-Token':'test-token'}).status_code,400)
            call.assert_not_called()

    def test_frame_is_no_store_jpeg(self):
        import base64
        self.authenticate()
        with patch.object(app.camera,'call',return_value={'jpeg':base64.b64encode(b'jpeg').decode()}):
            response=self.client.get('/api/camera/frame')
        self.assertEqual(response.data,b'jpeg');self.assertEqual(response.mimetype,'image/jpeg')
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_gallery_gets_are_private_read_only_and_jpeg_download_is_bounded(self):
        import base64
        self.authenticate()
        with patch.object(app.camera,'call',return_value=dict(indices=[0,5],total=2)) as call:
            response=self.client.get('/api/camera/photos/20261024T140545-e84c6aa5?storage=/mnt/ssd')
            self.assertEqual(response.status_code,200)
            call.assert_called_once_with(dict(action='photos',id='20261024T140545-e84c6aa5',storage='/mnt/ssd'))
            self.assertEqual(response.json['data']['indices'],[0,5])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        with patch.object(app.camera,'call',return_value=dict(jpeg=base64.b64encode(jpeg()).decode())) as call:
            response=self.client.get('/api/camera/photo/20261024T140545-e84c6aa5/5?storage=/mnt/ssd&download=1')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/jpeg')
            self.assertTrue(response.headers['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            call.assert_called_once_with(dict(action='photo',id='20261024T140545-e84c6aa5',index=5,storage='/mnt/ssd'))
        with patch.object(app.camera,'call',side_effect=ValueError('Không thấy ảnh')):
            self.assertEqual(self.client.get('/api/camera/photo/test/0').status_code,400)

    def test_beacon_accepts_body_csrf_and_scopes_viewer_to_session(self):
        self.authenticate()
        with patch.object(app.camera,'call',return_value={}) as call:
            response=self.client.post('/api/camera',json={'action':'watch','viewer':'a'*32,'watching':False,'csrf':'test-token'})
            self.assertEqual(response.status_code,200)
            scoped=call.call_args.args[0]['viewer']
            self.assertEqual(len(scoped),64)
            self.assertNotEqual(scoped,'a'*32)
        with patch.object(app.camera,'call') as call:
            self.assertEqual(self.client.post('/api/camera',json={'action':'watch','viewer':'a'*32,'watching':True}).status_code,403)
            call.assert_not_called()


if __name__=='__main__':unittest.main()
