import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import media_agent as m

class NonstopTests(unittest.TestCase):
    def setUp(self):
        m.NONSTOP=True;m.MANUAL_PAUSE=False;m.LAST_URL='https://www.youtube.com/watch?v=abcdefghijk'
        m.QUEUE.clear();m.RECOVERY_AT=0;m.RECOVERY_COUNT=0;m.LAST_PROGRESS=None;m.PROGRESS_AT=0
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=patch.object(m,'CONFIG',Path(self.temp.name)/'nonstop.json');p.start();self.addCleanup(p.stop)
        self.addCleanup(setattr,m,'NONSTOP',False);self.addCleanup(setattr,m,'MANUAL_PAUSE',False)
    def test_manual_pause_wins_without_browser_or_disk_action(self):
        m.MANUAL_PAUSE=True
        with patch.object(m,'evaluate') as e,patch.object(m,'open_browser') as o:
            m.nonstop_tick({'connected':False},100);e.assert_not_called();o.assert_not_called()
        self.assertFalse(m.CONFIG.exists())
    def test_healthy_tick_does_not_write_config(self):
        with patch.object(m,'evaluate',return_value=True),patch.object(m,'open_browser') as o:
            m.nonstop_tick({'connected':True,'has_video':True,'url':m.LAST_URL,'position':10},100)
            o.assert_not_called();self.assertFalse(m.CONFIG.exists())
    def test_failure_recovery_is_rate_limited(self):
        with patch.object(m,'open_browser') as o,patch.object(m,'play') as p:
            m.nonstop_tick({'connected':False},100)
            m.nonstop_tick({'connected':False},120)
            self.assertEqual(o.call_count,1);self.assertEqual(p.call_count,1)
            m.nonstop_tick({'connected':False},161)
            self.assertEqual(o.call_count,2);self.assertEqual(m.RECOVERY_AT,281)
    def test_ended_prefers_explicit_queue(self):
        m.QUEUE.append(m.LAST_URL)
        with patch.object(m,'evaluate',return_value=True),patch.object(m,'play') as p:
            m.nonstop_tick({'connected':True,'has_video':True,'ended':True},100);p.assert_not_called()
    def test_ads_not_reloaded(self):
        with patch.object(m,'evaluate',return_value=True),patch.object(m,'play') as p:
            m.nonstop_tick({'connected':True,'has_video':True,'ad':True,'notice':'buffering'},100);p.assert_not_called()
    def test_explicit_setting_persists_and_boolean_required(self):
        with patch.object(m,'status',return_value={'url':m.LAST_URL}):
            m.dispatch({'action':'nonstop','enabled':True})
            self.assertTrue(json.loads(m.CONFIG.read_text())['enabled'])
            with self.assertRaises(ValueError):m.dispatch({'action':'nonstop','enabled':'true'})
        m.NONSTOP=False;m.load_nonstop();self.assertTrue(m.NONSTOP)
    def test_dashboard_pause_persists_and_resume_clears(self):
        with patch.object(m,'status',return_value={'paused':False}),patch.object(m,'evaluate'):
            m.dispatch({'action':'toggle'});self.assertTrue(m.MANUAL_PAUSE)
        with patch.object(m,'status',return_value={'paused':True}),patch.object(m,'evaluate'):
            m.dispatch({'action':'toggle'});self.assertFalse(m.MANUAL_PAUSE)

if __name__=='__main__':unittest.main()
