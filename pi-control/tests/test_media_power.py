import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import media_agent as m
import app


class MediaPowerTests(unittest.TestCase):
    def setUp(self):
        self.saved = (m.STANDBY, m.LAST_URL, m.WS, m.NONSTOP, m.CONFIG, m.VOLUME, m.WAKE_URL, m.WAKE_UNTIL)
        self.tmp = tempfile.TemporaryDirectory()
        m.CONFIG = Path(self.tmp.name) / 'state.json'
        m.STANDBY = False
        m.WS = None

    def tearDown(self):
        m.STANDBY, m.LAST_URL, m.WS, m.NONSTOP, m.CONFIG, m.VOLUME, m.WAKE_URL, m.WAKE_UNTIL = self.saved
        self.tmp.cleanup()

    def test_stop_only_dedicated_browser_and_persist_intent(self):
        with patch.object(m, 'evaluate', return_value={'url':'https://www.youtube.com/watch?v=abcdefghijk','title':'test','up_next':None,'recommendations':[]}), patch.object(m.subprocess, 'run') as run:
            result = m.set_power(False)
            self.assertTrue(result['standby'])
            self.assertTrue(json.loads(m.CONFIG.read_text())['standby'])
            self.assertEqual(run.call_args.args[0], ['systemctl','--user','stop',m.unit('pi-media-browser')])

    def test_rest_status_and_nonstop_do_not_touch_browser(self):
        m.STANDBY = True
        m.NONSTOP = True
        with patch.object(m,'evaluate') as evaluate, patch.object(m,'open_browser') as start:
            self.assertTrue(m.status()['standby'])
            m.nonstop_tick({'connected':False})
            evaluate.assert_not_called()
            start.assert_not_called()
        with self.assertRaises(ValueError):m.dispatch({'action':'play','url':'https://youtu.be/abcdefghijk'})

    def test_restart_loads_rest_latch_and_blocks_open(self):
        m.STANDBY = True
        m.save_nonstop()
        m.STANDBY = False
        m.load_nonstop()
        self.assertTrue(m.STANDBY)
        with patch.object(m.subprocess,'run') as run, self.assertRaises(ValueError):m.open_browser()
        run.assert_not_called()

    def test_wake_starts_fixed_service_and_clears_latch(self):
        m.STANDBY = True
        with patch.object(m.subprocess,'run') as run, patch.object(m,'status',return_value={}):
            m.set_power(True)
        self.assertFalse(m.STANDBY)
        self.assertFalse(json.loads(m.CONFIG.read_text())['standby'])
        self.assertEqual(run.call_args.args[0],['systemctl','--user','start',m.unit('pi-media-browser')])

    def test_invalid_payloads_and_failed_stop_do_not_change_latch(self):
        for value in (None, 0, 1, 'false'):
            with self.assertRaises(ValueError):m.set_power(value)
        with patch.object(m,'status',return_value={}), patch.object(m.subprocess,'run',side_effect=RuntimeError), self.assertRaises(RuntimeError):m.set_power(False)
        self.assertFalse(m.STANDBY)

    def test_wake_failure_restores_latch(self):
        m.STANDBY = True
        with patch.object(m.subprocess,'run',side_effect=RuntimeError), self.assertRaises(RuntimeError):m.set_power(True)
        self.assertTrue(m.STANDBY)
        self.assertTrue(json.loads(m.CONFIG.read_text())['standby'])

    def test_power_requires_login_and_csrf(self):
        c = app.app.test_client()
        with patch.object(app.media,'call',return_value={'standby':True}) as call:
            self.assertEqual(c.post('/api/media',json={'action':'power','enabled':False}).status_code,302)
            with c.session_transaction() as s:s['logged_in']=True;s['csrf']='power-test'
            self.assertEqual(c.post('/api/media',json={'action':'power','enabled':False}).status_code,403)
            call.assert_not_called()
            self.assertEqual(c.post('/api/media',json={'action':'power','enabled':False},headers={'X-CSRF-Token':'power-test'}).status_code,200)

    def test_stop_preserves_actual_video_volume(self):
        m.VOLUME=100
        with patch.object(m,'status',return_value={'url':'https://www.youtube.com/watch?v=abcdefghijk','has_video':True,'volume':61}), patch.object(m.subprocess,'run'):
            m.set_power(False)
        self.assertEqual(json.loads(m.CONFIG.read_text())['volume'],61)

    def test_wake_navigates_saved_video_instead_of_homepage_preview(self):
        m.STANDBY=True;m.NONSTOP=True;m.LAST_URL='https://www.youtube.com/watch?v=abcdefghijk'
        with patch.object(m,'MANUAL_PAUSE',False),patch.object(m.POLICY,'sleep_state',return_value={'expired':False}),patch.object(m.POLICY,'reason',return_value=None),patch.object(m.subprocess,'run'),patch.object(m,'status',return_value={'has_video':True,'url':''}):
            m.set_power(True)
            with patch.object(m,'play') as play:
                m.resume_tick();play.assert_called_once_with(m.LAST_URL)
            self.assertEqual(m.WAKE_URL,'')
