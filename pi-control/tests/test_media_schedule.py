from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import media_agent as m

class MediaScheduleTests(unittest.TestCase):
    def setUp(self):
        self.old=m.VOLUME_SCHEDULE.copy();self.volume=m.VOLUME
        m.VOLUME_SCHEDULE=dict(enabled=True,start='22:00',end='07:00',limit=30)
        self.addCleanup(setattr,m,'VOLUME_SCHEDULE',self.old)
        self.addCleanup(setattr,m,'VOLUME',self.volume)
        m.QUEUE.clear()

    def test_midnight_window_boundaries(self):
        for hour,minute,active in [(21,59,False),(22,0,True),(23,59,True),(0,0,True),(6,59,True),(7,0,False)]:
            with self.subTest(hour=hour,minute=minute):
                self.assertEqual(m.volume_policy(datetime(2026,10,18,hour,minute))['active'],active)

    def test_daytime_window_and_disabled(self):
        m.VOLUME_SCHEDULE.update(start='09:00',end='17:00')
        self.assertTrue(m.volume_policy(datetime(2026,10,18,12))['active'])
        self.assertFalse(m.volume_policy(datetime(2026,10,18,23))['active'])
        m.VOLUME_SCHEDULE['enabled']=False
        self.assertFalse(m.volume_policy(datetime(2026,10,18,12))['active'])

    def test_reject_bad_settings(self):
        for change in [dict(enabled='yes'),dict(start='24:00'),dict(end='7:00'),dict(end='22:00'),dict(limit=True),dict(limit=-1),dict(limit=101)]:
            with self.subTest(change=change),self.assertRaises(ValueError):m.validate_schedule(dict(m.VOLUME_SCHEDULE,**change))

    def test_tick_lowers_without_disk_write_or_playback_resume(self):
        with patch.object(m,'volume_policy',return_value=dict(active=True,limit=30)),patch.object(m,'evaluate') as e,patch.object(m,'install_volume_hook'),patch.object(m,'save_nonstop') as save:
            m.volume_tick(dict(has_video=True,volume=80,paused=True))
            self.assertEqual(m.VOLUME,30);self.assertNotIn('play()',e.call_args.args[0]);save.assert_not_called()
        with patch.object(m,'volume_policy',return_value=dict(active=False,limit=30)),patch.object(m,'evaluate') as e:
            m.volume_tick(dict(has_video=True,volume=30));e.assert_not_called();self.assertEqual(m.VOLUME,30)

    def test_command_cannot_exceed_active_cap(self):
        with patch.object(m,'volume_policy',return_value=dict(active=True,limit=30)),patch.object(m,'evaluate') as e,patch.object(m,'install_volume_hook'),patch.object(m,'status',return_value={}),patch.object(m,'save_nonstop'):
            m.dispatch(dict(action='volume',value=95));self.assertEqual(m.VOLUME,30)
            self.assertIn('v.volume=30/100',e.call_args.args[0])

    def test_schedule_survives_empty_seed_url(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'CONFIG',Path(folder)/'config.json'):
            m.save_nonstop();m.VOLUME_SCHEDULE['enabled']=False;m.load_nonstop()
            self.assertTrue(m.VOLUME_SCHEDULE['enabled'])

    def test_upcoming_sanitized_and_queue_has_priority(self):
        base=dict(url='https://youtu.be/abcdefghijk',title='Current',has_video=True,up_next=dict(url='https://evil.example/',title='Bad'))
        with patch.object(m,'evaluate',side_effect=lambda _:json.loads(json.dumps(base))):
            self.assertIsNone(m.status()['up_next'])
            base['up_next']=dict(url='https://youtu.be/12345678901',title='Recommendation')
            self.assertEqual(m.status()['up_next']['title'],'Recommendation')
            m.QUEUE.append('https://www.youtube.com/watch?v=ABCDEFGHIJK')
            self.assertEqual(m.status()['up_next']['source'],'Hàng đợi của bạn')
        m.QUEUE.clear()

    def test_skip_uses_validated_recommendation(self):
        with patch.object(m,'play') as play,patch.object(m,'status',return_value={'up_next':dict(url='https://youtu.be/12345678901')}),patch.object(m,'save_nonstop'):
            m.dispatch(dict(action='next'));play.assert_called_once_with('https://www.youtube.com/watch?v=12345678901')
        with patch.object(m,'status',return_value={'up_next':dict(url='https://evil.example/')}),patch.object(m,'play') as play,self.assertRaises(ValueError):
            m.dispatch(dict(action='next'))
        play.assert_not_called()

if __name__=='__main__':unittest.main()
