import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import media_agent as m
from media_extras import Shortcuts, CommandReceipt, BluetoothGuard, youtube_destination
from media_policy import PlaybackPolicy


TRACK = 'https://open.spotify.com/track/1234567890ABCDEFGHIJKL'
PLAYLIST = 'https://www.youtube.com/playlist?list=PLabcdefghijk1234567890'
VIDEO = 'https://www.youtube.com/watch?v=abcdefghijk'


def output(name='bluez_output.test.1'):
    return dict(devices=[dict(name=name, kind='output')], defaults={'output': name}, errors=[])


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'shortcuts.json'
        self.store = Shortcuts(self.path)

    def test_reads_never_create_file_and_saved_items_survive_restart(self):
        self.assertEqual(self.store.rows(), []); self.assertFalse(self.path.exists())
        self.store.add('youtube', PLAYLIST, 'Nhạc làm việc')
        self.store.add('spotify', TRACK+'?si=private', 'Spotify')
        first = self.path.stat().st_mtime_ns
        self.assertEqual(Shortcuts(self.path).rows(), self.store.rows())
        self.store.rows(); self.assertEqual(self.path.stat().st_mtime_ns, first)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private', self.path.read_text())

    def test_duplicate_is_updated_without_duplicate_or_redundant_write(self):
        self.store.add('youtube', PLAYLIST, 'One')
        before = self.path.stat().st_mtime_ns
        self.store.add('youtube', PLAYLIST, 'One')
        self.assertEqual(self.path.stat().st_mtime_ns, before)
        self.store.add('youtube', PLAYLIST, 'Two')
        self.assertEqual([row['label'] for row in self.store.rows()], ['Two'])

    def test_limit_delete_and_invalid_id(self):
        for i in range(24):
            self.store.add('youtube', VIDEO+'&list=PLabcdefghijk'+str(i), str(i))
        with self.assertRaises(ValueError): self.store.add('spotify', TRACK, 'Too many')
        ident = self.store.rows()[0]['id']; self.store.remove(ident)
        with self.assertRaises(ValueError): self.store.get(ident)
        with self.assertRaises(ValueError): self.store.remove('../file')
        self.assertEqual(len(self.store.rows()), 23)

    def test_failed_write_preserves_previous_items(self):
        self.store.add('youtube', VIDEO, 'One'); before = self.path.read_bytes()
        with patch.object(self.store, 'save', side_effect=OSError('full disk')):
            with self.assertRaises(OSError): self.store.add('spotify', TRACK, 'Two')
        self.assertEqual(len(self.store.rows()), 1); self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_file_is_not_silently_replaced_on_second_attempt(self):
        self.path.write_text('{broken')
        for _ in range(2):
            with self.assertRaises(ValueError): self.store.add('youtube', VIDEO, 'One')
        self.assertEqual(self.path.read_text(), '{broken')

    def test_strict_urls_and_labels(self):
        self.assertEqual(youtube_destination(VIDEO+'&list=PLabcdefghijk&si=private'), VIDEO+'&list=PLabcdefghijk')
        for url in ('http://youtube.com/playlist?list=PLabcdefghijk', 'https://youtube.com.evil/playlist?list=PLabcdefghijk',
                    'https://user@youtube.com/playlist?list=PLabcdefghijk', 'https://youtube.com:0/playlist?list=PLabcdefghijk',
                    'https://youtube.com/results?search_query=x', 'file:///etc/passwd', None):
            with self.subTest(url=url), self.assertRaises(ValueError): self.store.add('youtube', url, 'Name')
        for label in ('', 'a'*61, 'Bad\nName', None):
            with self.subTest(label=label), self.assertRaises(ValueError): self.store.add('youtube', VIDEO, label)


class ReceiptTests(unittest.TestCase):
    def test_toggle_waits_for_observed_pause_and_expires(self):
        r = CommandReceipt(); r.begin('toggle', {'paused':False}, {'paused':True}, now=10)
        self.assertEqual(r.observe(dict(connected=True, has_video=True, paused=False), now=11)['state'], 'pending')
        self.assertEqual(r.observe(dict(connected=True, has_video=True, paused=False), now=23)['state'], 'unconfirmed')
        r.begin('toggle', {}, {'paused':True}, now=30)
        self.assertEqual(r.observe(dict(connected=True, has_video=True, paused=True), now=31)['state'], 'confirmed')

    def test_play_requires_correct_provider_target_and_actual_playback(self):
        r = CommandReceipt(); r.begin('shortcut_play', {}, dict(provider='spotify', url=TRACK), now=1)
        state = dict(provider='spotify', url=TRACK, connected=True, has_video=True, paused=False,track_matches=True)
        for changes in ({'provider':'youtube'}, {'url':VIDEO}, {'paused':True}, {'launch_pending':True}, {'login_required':True},{'track_matches':False}):
            self.assertEqual(r.observe(state|changes, now=2)['state'], 'pending')
        self.assertEqual(r.observe(state, now=3)['state'], 'confirmed')

    def test_next_requires_content_change_and_volume_cap_is_observed(self):
        r = CommandReceipt(); state = dict(url=VIDEO, title='One', connected=True, has_video=True, paused=False)
        r.begin('next', state, {}, now=1)
        self.assertEqual(r.observe(state, now=2)['state'], 'pending')
        self.assertEqual(r.observe(state|{'title':'Two'}, now=3)['state'], 'confirmed')
        r.begin('volume', {}, {'volume':30}, now=1)
        self.assertEqual(r.observe(state|{'volume':100}, now=2)['state'], 'pending')
        self.assertEqual(r.observe(state|{'volume':30}, now=3)['state'], 'confirmed')

    def test_unknown_volume_or_progress_cannot_confirm(self):
        r = CommandReceipt(); r.begin('volume', {}, {'volume':0}, now=1)
        self.assertEqual(r.observe(dict(connected=True, volume=0, can_volume=False), now=2)['state'], 'pending')
        r.begin('seek', {}, {'position':10}, now=1)
        self.assertEqual(r.observe(dict(connected=True, position=10, position_known=False), now=2)['state'], 'pending')

    def test_play_confirmation_requires_progress_and_ignores_ads(self):
        r=CommandReceipt()
        r.begin('play', {}, dict(provider='youtube',url=VIDEO), now=1)
        state=dict(connected=True,has_video=True,paused=False,url=VIDEO,position_known=True,position=0)
        self.assertEqual(r.observe(state, now=2)['state'], 'pending')
        self.assertEqual(r.observe(state|{'position':2,'ad':True}, now=3)['state'], 'pending')
        self.assertEqual(r.observe(state, now=4)['state'], 'pending')
        self.assertEqual(r.observe(state, now=5)['state'], 'pending')
        self.assertEqual(r.observe(state|{'position':1}, now=6)['state'], 'confirmed')


class BluetoothGuardTests(unittest.TestCase):
    def test_only_loss_of_selected_bluetooth_route_latches_and_never_auto_resumes(self):
        guard = BluetoothGuard()
        self.assertFalse(guard.observe(output(), now=1))
        self.assertTrue(guard.observe(output('alsa_output.analog'), now=2))
        self.assertTrue(guard.latched)
        self.assertFalse(guard.observe(output(), now=3))
        self.assertTrue(guard.latched, 'Reconnect must not start playback')
        guard.resume(now=4); self.assertFalse(guard.latched)

    def test_other_bluetooth_device_or_intentional_route_change_is_not_loss(self):
        guard = BluetoothGuard(); data = output('alsa_output.analog')
        data['devices'].append(dict(name='bluez_output.spare',kind='output'))
        guard.observe(data, now=1)
        self.assertFalse(guard.observe(output('alsa_output.analog'), now=2))
        self.assertFalse(guard.latched)
        guard.observe(output(), now=3)
        mixed = output('alsa_output.analog');mixed['devices'] += output()['devices']
        guard.observe(mixed, now=4)
        self.assertFalse(guard.observe(output('alsa_output.analog'), now=5))

    def test_audio_errors_are_bounded_and_resume_requires_fresh_confirmed_route(self):
        guard = BluetoothGuard(); guard.observe(output(), now=1)
        self.assertFalse(guard.observe(None, now=2)); self.assertTrue(guard.observe(None, now=3))
        with self.assertRaises(ValueError): guard.resume(now=4)
        guard.observe(output(), now=5)
        with self.assertRaises(ValueError): guard.resume(now=20)
        guard.observe(output(), now=21); guard.resume(now=22)
        self.assertFalse(guard.latched)

    def test_disabled_does_not_pause_or_require_hardware_to_release(self):
        guard = BluetoothGuard(); guard.observe(output(), now=1);guard.enabled=False
        self.assertFalse(guard.observe(output('alsa_output.analog'), now=2))
        guard.latched=True;guard.resume(now=100);self.assertFalse(guard.latched)


class MediaExtrasIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        scope=patch.multiple(m,PROVIDER='youtube',STANDBY=False,NONSTOP=False,MANUAL_PAUSE=False,
            CONFIG=self.root/'nonstop.json',SHORTCUTS=Shortcuts(self.root/'shortcuts.json'),
            BT_GUARD=BluetoothGuard(),RECEIPT=CommandReceipt(),GUARD_SCRIPT=None,GUARD_TARGET='',GUARD_FILE=self.root/'hold.json',
            YOUTUBE_PENDING=None,YOUTUBE_LIST='',WAKE_URL='',SPOTIFY_PENDING=0,POLICY=PlaybackPolicy())
        scope.start();self.addCleanup(scope.stop)

    def test_shortcut_management_works_in_standby_and_never_opens_browser(self):
        m.STANDBY=True
        with patch.object(m,'open_browser') as browser:
            m.run_command(dict(action='shortcut_save',provider='youtube',url=PLAYLIST,label='Work'))
            self.assertEqual(len(m.status()['shortcuts']),1)
            browser.assert_not_called()
        self.assertEqual(m.status()['command']['state'],'confirmed')

    def test_shortcut_spotify_play_explicitly_selects_source_without_touching_accounts(self):
        m.SHORTCUTS.add('spotify',TRACK,'Work');ident=m.SHORTCUTS.rows()[0]['id']
        def source(provider):m.PROVIDER=provider
        with patch.object(m,'select_source',side_effect=source) as switch,patch.object(m,'spotify_dispatch',return_value={}) as play:
            m.dispatch(dict(action='shortcut_play',id=ident))
        switch.assert_called_once_with('spotify');play.assert_called_once_with(dict(action='play',url=TRACK))

    def test_youtube_playlist_opens_only_matching_first_video(self):
        with patch.object(m,'install_volume_hook'),patch.object(m,'cdp') as cdp,patch.object(m,'status',return_value={}):
            m.dispatch(dict(action='play',url=PLAYLIST))
        cdp.assert_called_once_with('Page.navigate',{'url':PLAYLIST})
        with patch.object(m,'target',return_value={'url':PLAYLIST}),patch.object(m,'evaluate',return_value=VIDEO+'&list=PLdifferent987654'),patch.object(m,'play') as play:
            m.playlist_tick();play.assert_not_called()
        with patch.object(m,'target',return_value={'url':PLAYLIST}),patch.object(m,'evaluate',return_value=VIDEO+'&list=PLabcdefghijk1234567890'),patch.object(m,'play') as play:
            m.playlist_tick();play.assert_called_once_with(VIDEO)
        self.assertIsNone(m.YOUTUBE_PENDING)

    def test_bluetooth_hold_cancels_wake_and_pending_play_and_mutes_before_pause(self):
        m.WAKE_URL=VIDEO;m.SPOTIFY_PENDING=100;m.YOUTUBE_PENDING=(PLAYLIST,100)
        with patch.object(m,'cdp',return_value={'identifier':'hold-script'}),patch.object(m,'target',return_value={'id':'page'}),patch.object(m,'evaluate') as evaluate:
            m.hold_bluetooth()
        self.assertTrue(m.MANUAL_PAUSE);self.assertEqual(m.WAKE_URL,'');self.assertEqual(m.SPOTIFY_PENDING,0)
        self.assertIsNone(m.YOUTUBE_PENDING);evaluate.assert_called_once_with(m.SAFETY_MUTE_JS)

    def test_hold_survives_agent_restart_in_ram_and_explicit_release_removes_hook(self):
        with patch.object(m,'cdp',return_value={'identifier':'hold-script'}),patch.object(m,'target',return_value={'id':'page'}),patch.object(m,'evaluate'):
            m.hold_bluetooth()
        m.GUARD_SCRIPT=None;m.BT_GUARD.latched=False;m.MANUAL_PAUSE=False
        m.load_bluetooth_hold();self.assertTrue(m.BT_GUARD.latched);self.assertTrue(m.MANUAL_PAUSE)
        self.assertEqual(m.GUARD_FILE.stat().st_mode&0o777,0o600)
        m.BT_GUARD.observe(output(),now=1)
        with patch.object(m.BT_GUARD,'resume',side_effect=lambda:setattr(m.BT_GUARD,'latched',False)),patch.object(m,'target',return_value={'id':'page'}),patch.object(m,'cdp') as cdp,patch.object(m,'evaluate'):
            m.release_bluetooth()
        cdp.assert_called_once_with('Page.removeScriptToEvaluateOnNewDocument',{'identifier':'hold-script'})
        self.assertFalse(m.GUARD_FILE.exists())

    def test_guard_settings_roll_back_if_save_fails_and_status_does_not_write(self):
        with patch.object(m,'save_nonstop',side_effect=OSError('full')):
            with self.assertRaises(OSError):m.dispatch(dict(action='bluetooth_guard',enabled=False))
        self.assertTrue(m.BT_GUARD.enabled)
        m.STANDBY=True
        with patch.object(m,'save_nonstop') as save:
            for _ in range(3):m.status()
        save.assert_not_called();self.assertFalse(m.SHORTCUTS.path.exists())

    def test_invalid_play_does_not_release_guard(self):
        m.BT_GUARD.latched=True
        with patch.object(m,'player_status',return_value={}),patch.object(m,'release_bluetooth') as release:
            with self.assertRaises(ValueError):m.run_command(dict(action='play',url='https://evil.test/'))
        release.assert_not_called()

    def test_spotify_with_no_media_element_rests_browser_on_bluetooth_loss(self):
        m.PROVIDER='spotify';m.BT_GUARD.latched=True
        with patch.object(m,'target',return_value={'id':'page'}),patch.object(m,'cdp',return_value={'identifier':'hold-script'}),patch.object(m,'evaluate',return_value=0),patch.object(m,'set_power') as power:
            m.hold_bluetooth()
        power.assert_called_once_with(False)
        self.assertTrue(m.BT_GUARD.latched);self.assertTrue(m.MANUAL_PAUSE)


if __name__ == '__main__':unittest.main()
