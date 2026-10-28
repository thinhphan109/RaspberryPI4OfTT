import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from media_policy import PlaybackPolicy
import media_agent as m

A='https://www.youtube.com/watch?v=abcdefghijk'
B='https://www.youtube.com/watch?v=12345678901'
C='https://www.youtube.com/watch?v=ABCDEFGHIJK'

class PolicyTests(unittest.TestCase):
    def test_history_window_and_manual_override(self):
        p=PlaybackPolicy();p.observe('abcdefghijk',100)
        self.assertTrue(p.reason('abcdefghijk',now=101))
        self.assertFalse(p.reason('abcdefghijk',automatic=False,now=101))
        self.assertFalse(p.reason('abcdefghijk',now=10900))
        p.dislike('abcdefghijk','Song');self.assertTrue(p.reason('abcdefghijk',automatic=False,now=10901))

    def test_bounds_and_invalid_preferences(self):
        p=PlaybackPolicy()
        for i in range(600):p.observe(str(i).zfill(11),i)
        self.assertEqual(len(p.history),500)
        for i in range(200):p.dislike(str(i).zfill(11),'x')
        with self.assertRaises(ValueError):p.dislike('abcdefghijk','full')
        for value in [True,0,721,1.5]:
            with self.subTest(value=value),self.assertRaises(ValueError):p.start_sleep(value,50)
        for value in [dict(enabled=True,hours=0),dict(enabled='true',hours=3),dict(enabled=True,hours=True)]:
            with self.subTest(value=value),self.assertRaises(ValueError):p.configure_repeat(value)

    def test_sleep_fade_and_expiry(self):
        p=PlaybackPolicy();p.start_sleep(3,80,now=100,wall=1000)
        self.assertEqual(p.sleep_cap(100),80)
        self.assertEqual(p.sleep_cap(220),40)
        self.assertEqual(p.sleep_cap(280),0)
        self.assertTrue(p.sleep_state(280)['expired'])
        p.cancel_sleep();self.assertEqual(p.sleep_cap(280),100)

    def test_restart_preserves_expired_latch_but_not_history(self):
        p=PlaybackPolicy();p.start_sleep(1,50,now=100,wall=1000);p.observe('abcdefghijk',100)
        saved=json.loads(json.dumps(p.dump()))
        q=PlaybackPolicy()
        with patch('media_policy.time.time',return_value=1100),patch('media_policy.time.monotonic',return_value=300):q.load(saved)
        self.assertTrue(q.sleep_state(300)['expired']);self.assertEqual(len(q.history),0)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.p=patch.object(m,'POLICY',PlaybackPolicy());self.p.start();self.addCleanup(self.p.stop)
        for name in ('MANUAL_PAUSE','NONSTOP','POLICY_NOTE','POLICY_RETRY_AT','VOLUME','LAST_URL'):
            value=getattr(m,name);self.addCleanup(setattr,m,name,value)
        m.QUEUE.clear();self.addCleanup(m.QUEUE.clear)
        m.POLICY_RETRY_AT=0;m.NONSTOP=True;m.MANUAL_PAUSE=False
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        p=patch.object(m,'CONFIG',Path(folder.name)/'config.json');p.start();self.addCleanup(p.stop)

    def test_pick_skips_recent_and_disliked_candidates(self):
        m.POLICY.observe('12345678901');m.POLICY.dislike('ABCDEFGHIJK','no')
        rows=[dict(url=B,title='recent'),dict(url=C,title='bad'),dict(url='https://evil.test'),dict(url=A,title='allowed')]
        self.assertEqual(m.next_video('',rows)['url'],A)
        self.assertIsNone(m.next_video(A,rows))

    def test_queue_priority_and_filtered_index(self):
        m.POLICY.dislike('abcdefghijk','no');m.QUEUE.extend([A,B])
        choice=m.next_video(C,[dict(url=C)])
        with patch.object(m,'play') as play:m.move_next(dict(up_next=choice))
        play.assert_called_once_with(B);self.assertEqual(m.QUEUE,[A])

    def test_native_navigation_to_recent_is_redirected(self):
        m.POLICY.observe('abcdefghijk');m.POLICY.observe('12345678901')
        with patch.object(m,'play') as play:
            self.assertTrue(m.preference_tick(dict(url=A,has_video=True,up_next=dict(url=C)),now=100))
        play.assert_called_once_with(C)

    def test_exhausted_candidates_pause_without_periodic_write(self):
        m.POLICY.dislike('abcdefghijk','no')
        with patch.object(m,'evaluate') as e,patch.object(m,'save_nonstop') as save:
            m.preference_tick(dict(url=A,up_next=None),now=100)
            e.assert_called_once_with(m.PAUSE_JS);save.assert_not_called();self.assertTrue(m.MANUAL_PAUSE)

    def test_expiry_stops_nonstop_without_persistent_writes(self):
        m.POLICY.start_sleep(1,40,now=0,wall=0)
        with patch('media_policy.time.monotonic',return_value=61),patch.object(m,'evaluate') as e,patch.object(m,'open_browser') as start,patch.object(m,'play') as play,patch.object(m,'save_nonstop') as save:
            self.assertTrue(m.sleep_tick(dict(connected=True)))
            m.nonstop_tick(dict(connected=False))
            e.assert_called_once_with(m.PAUSE_JS);start.assert_not_called();play.assert_not_called();save.assert_not_called()

    def test_expired_timer_rejects_next_and_explicit_resume_clears_latch(self):
        m.POLICY.start_sleep(1,40,now=0,wall=0)
        with patch('media_policy.time.monotonic',return_value=61),patch.object(m,'evaluate') as e,patch.object(m,'install_volume_hook'),patch.object(m,'status',return_value=dict(paused=True)):
            with self.assertRaises(ValueError):m.play(A)
            m.dispatch(dict(action='toggle'));self.assertIsNone(m.POLICY.sleep)
            self.assertFalse(m.MANUAL_PAUSE);self.assertIn('await v.play()',e.call_args.args[0])

    def test_cancel_expired_does_not_resume(self):
        m.POLICY.start_sleep(1,40,now=0,wall=0)
        with patch('media_policy.time.monotonic',return_value=61),patch.object(m,'status',return_value={}),patch.object(m,'evaluate') as e:
            with self.assertRaises(ValueError):m.dispatch(dict(action='sleep_cancel'))
            self.assertTrue(m.POLICY.sleep_state()['expired']);e.assert_not_called()

    def test_dislike_persists_skips_and_undo(self):
        s=dict(url=A,title='Unwanted',has_video=True,up_next=dict(url=B))
        with patch.object(m,'status',return_value=s),patch.object(m,'play') as play:
            m.dispatch(dict(action='dislike'));play.assert_called_once_with(B)
            self.assertIn('abcdefghijk',json.loads(m.CONFIG.read_text())['preferences']['disliked'])
            m.dispatch(dict(action='undislike',id='abcdefghijk'));self.assertFalse(m.POLICY.disliked)

    def test_explicit_play_overrides_repeat_but_not_dislike(self):
        m.POLICY.observe('abcdefghijk')
        with patch.object(m,'status',return_value={}),patch.object(m,'play') as play:
            m.dispatch(dict(action='play',url=A));play.assert_called_once_with(A)
            m.POLICY.dislike('abcdefghijk','no')
            with self.assertRaises(ValueError):m.dispatch(dict(action='play',url=A))

    def test_config_round_trip_without_seed(self):
        m.LAST_URL='';m.POLICY.dislike('abcdefghijk','A');m.POLICY.start_sleep(30,40)
        m.save_nonstop();m.POLICY=PlaybackPolicy();m.load_nonstop()
        self.assertIn('abcdefghijk',m.POLICY.disliked);self.assertTrue(m.POLICY.sleep_state()['active'])

    def test_sleep_and_night_cap_use_lower_level(self):
        m.POLICY.start_sleep(2,80,now=0,wall=0)
        with patch('media_policy.time.monotonic',return_value=30),patch.object(m,'volume_policy',return_value=dict(active=True,limit=30)):
            self.assertEqual(m.limited_volume(100),30)
        with patch('media_policy.time.monotonic',return_value=105),patch.object(m,'volume_policy',return_value=dict(active=True,limit=30)):
            self.assertEqual(m.limited_volume(100),10)

    def test_timer_setting_failure_restores_previous_timer(self):
        m.POLICY.start_sleep(30,50);old=m.POLICY.sleep.copy();deadline=m.POLICY.deadline
        with patch.object(m,'status',return_value=dict(has_video=True,volume=20)),patch.object(m,'save_nonstop',side_effect=OSError('disk unavailable')),self.assertRaises(OSError):
            m.dispatch(dict(action='sleep',minutes=5))
        self.assertEqual(m.POLICY.sleep,old);self.assertEqual(m.POLICY.deadline,deadline)

if __name__=='__main__':unittest.main()
