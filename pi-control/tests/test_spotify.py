import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import media_agent as m
import spotify_player as s
from media_policy import PlaybackPolicy


TRACK='https://open.spotify.com/track/1234567890ABCDEFGHIJKL'


class SpotifyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        scope=patch.multiple(m,PROVIDER='youtube',SPOTIFY_URL=s.HOME,SPOTIFY_AD_FILTER=True,SPOTIFY_PENDING=0,
                             LAST_URL='https://www.youtube.com/watch?v=abcdefghijk',STANDBY=False,NONSTOP=True,
                             MANUAL_PAUSE=False,QUEUE=[],POLICY=PlaybackPolicy(),ERROR='',
                             CONFIG=Path(temp.name)/'nonstop.json',WAKE_URL='')
        scope.start();self.addCleanup(scope.stop)

    def test_urls_canonical_and_strict_origins(self):
        self.assertEqual(s.url(TRACK+'?si=private-share-value'),TRACK)
        self.assertEqual(s.url(TRACK.replace('/track/','/intl-vi/track/')),TRACK)
        for value in [None,'http://open.spotify.com/','https://open.spotify.com.evil/',
                      'https://user@open.spotify.com/','https://open.spotify.com:0/',
                      'https://open.spotify.com:443/','https://open.spotify.com/search/pass',
                      'https://spotify.link/abcdef','file:///etc/passwd','https://accounts.spotify.com/login']:
            with self.subTest(value=value),self.assertRaises(ValueError):s.url(value)
        self.assertFalse(s.is_page('https://open.spotify.com.evil/'))
        self.assertTrue(s.is_page(s.LOGIN,auth=True));self.assertFalse(s.is_page(s.LOGIN))

    def test_public_state_allowlist_sanitizes_artwork_urls_and_invalid_numbers(self):
        result=s.state(dict(title='x'*400,artist='Artist',url=TRACK,artwork='https://evil.test/image',
                            token='SECRET',email='private@example.test',cookie='SECRET',position=float('nan'),volume=999))
        self.assertEqual(len(result['title']),300);self.assertEqual(result['artwork'],'')
        self.assertEqual(result['position'],0);self.assertEqual(result['volume'],100)
        self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('email',result)

    def test_login_page_status_never_evaluates_form_dom(self):
        m.PROVIDER='spotify'
        with patch.object(m,'target',return_value={'url':s.LOGIN}),patch.object(m,'evaluate') as evaluate:
            result=m.status()
        self.assertTrue(result['login_required']);evaluate.assert_not_called()
        self.assertNotIn('url',result)

    def test_source_switch_preserves_youtube_url_and_queue_and_saves_only_explicitly(self):
        m.QUEUE.append(m.LAST_URL)
        with patch.object(m,'open_browser'),patch.object(m,'evaluate'),patch.object(m,'install_volume_hook'),patch.object(m,'cdp') as cdp,patch.object(m,'spotify_status',return_value={}):
            m.select_source('spotify')
        self.assertEqual(m.PROVIDER,'spotify');self.assertEqual(len(m.QUEUE),1)
        self.assertIn('youtube.com',m.LAST_URL)
        cdp.assert_called_once_with('Page.navigate',{'url':s.HOME})
        saved=json.loads(m.CONFIG.read_text());self.assertEqual(saved['provider'],'spotify')
        self.assertEqual(m.CONFIG.stat().st_mode&0o777,0o600)

    def test_bad_source_and_standby_do_not_open_browser_or_write_settings(self):
        with patch.object(m,'open_browser') as browser:
            with self.assertRaises(ValueError):m.select_source('arbitrary')
            m.STANDBY=True
            with self.assertRaises(ValueError):m.select_source('spotify')
            browser.assert_not_called()
        self.assertFalse(m.CONFIG.exists())

    def test_no_youtube_recovery_or_queue_actions_while_spotify_selected(self):
        m.PROVIDER='spotify';m.QUEUE.append(m.LAST_URL)
        with patch.object(m,'play') as play,patch.object(m,'open_browser') as browser:
            m.nonstop_tick({'connected':False},now=1000)
            with self.assertRaises(ValueError):m.dispatch({'action':'enqueue','url':m.LAST_URL})
        play.assert_not_called();browser.assert_not_called();self.assertEqual(len(m.QUEUE),1)

    def test_status_and_spotify_tick_do_not_persist_playback_samples(self):
        m.PROVIDER='spotify'
        raw=dict(title='Song',url=TRACK,has_video=True,paused=False,volume=30,can_toggle=True)
        with patch.object(m,'target',return_value={'url':TRACK}),patch.object(m,'evaluate',return_value=raw),patch.object(m,'save_nonstop') as save,patch.object(m,'volume_tick'),patch.object(m,'sleep_tick',return_value=False),patch.object(s,'ad_filter') as ads:
            for _ in range(3):m.status();m.spotify_tick()
            save.assert_not_called();self.assertEqual(ads.call_count,3)
        self.assertEqual(m.SPOTIFY_URL,s.HOME)

    def test_controls_validate_before_javascript_and_manual_pause_cancels_pending_play(self):
        m.PROVIDER='spotify'
        with patch.object(m,'target',return_value={'url':TRACK}),patch.object(m,'evaluate') as evaluate:
            for payload in [dict(action='volume',value=True),dict(action='volume',value=float('nan')),dict(action='volume',value=101),dict(action='seek',value=99)]:
                with self.subTest(payload=payload),self.assertRaises(ValueError):m.dispatch(payload)
            evaluate.assert_not_called()
        m.SPOTIFY_PENDING=100
        with patch.object(m,'target',return_value={'url':TRACK}),patch.object(m,'status',return_value={'paused':False}),patch.object(s,'control'),patch.object(m,'save_nonstop'):
            m.spotify_dispatch({'action':'toggle'})
        self.assertTrue(m.MANUAL_PAUSE);self.assertEqual(m.SPOTIFY_PENDING,0)

    def test_sleep_on_spotify_keeps_saved_youtube_url(self):
        m.PROVIDER='spotify';original=m.LAST_URL
        with patch.object(m,'status',return_value={'url':TRACK,'has_video':True,'volume':30}):
            m.dispatch({'action':'sleep','minutes':10})
        self.assertEqual(m.LAST_URL,original)
        self.assertTrue(m.POLICY.sleep_state()['active'])

    def test_ad_filter_requires_bool_and_login_action_only_navigates_to_fixed_official_url(self):
        m.PROVIDER='spotify'
        with patch.object(m,'cdp') as cdp,patch.object(m,'status',return_value={}):
            m.dispatch({'action':'spotify_login','password':'ignored'})
        cdp.assert_called_once_with('Page.navigate',{'url':s.LOGIN})
        for bad in ['true',1,None]:
            with self.assertRaises(ValueError):m.dispatch({'action':'spotify_filter','enabled':bad})

    def test_provider_settings_survive_restart_and_keep_old_configuration_compatible(self):
        m.PROVIDER='spotify';m.SPOTIFY_URL=TRACK;m.SPOTIFY_AD_FILTER=False;m.save_nonstop()
        m.PROVIDER='youtube';m.SPOTIFY_URL=s.HOME;m.SPOTIFY_AD_FILTER=True;m.load_nonstop()
        self.assertEqual(m.PROVIDER,'spotify');self.assertEqual(m.SPOTIFY_URL,TRACK);self.assertFalse(m.SPOTIFY_AD_FILTER)
        m.CONFIG.write_text(json.dumps({'url':m.LAST_URL,'enabled':True}))
        m.load_nonstop();self.assertEqual(m.PROVIDER,'youtube')

    def test_play_after_spotify_sleep_restores_volume_before_navigation(self):
        m.PROVIDER='spotify';m.POLICY.start_sleep(1,60);m.POLICY.deadline=0;m.VOLUME=0
        with patch.object(m,'install_volume_hook') as hook,patch.object(m,'cdp') as cdp,patch.object(m,'status',return_value={}):
            m.spotify_dispatch({'action':'play','url':TRACK})
        hook.assert_called_once_with(60);self.assertEqual(m.VOLUME,60)
        self.assertFalse(m.POLICY.sleep_state()['expired'])
        cdp.assert_called_once_with('Page.navigate',{'url':TRACK})

    def test_spotify_wake_navigates_correct_provider_even_when_manually_paused(self):
        m.PROVIDER='spotify';m.MANUAL_PAUSE=True;m.WAKE_URL=s.HOME
        with patch.object(m,'WAKE_UNTIL',1e12),patch.object(m,'install_volume_hook'),patch.object(m,'cdp') as cdp,patch.object(m,'play') as youtube:
            m.resume_tick()
        cdp.assert_called_once_with('Page.navigate',{'url':s.HOME});youtube.assert_not_called()

    def test_switch_away_pauses_before_restoring_ad_mute(self):
        m.PROVIDER='spotify';playing=[True]
        def evaluate(script):
            if script==s.PAUSE_JS:playing[0]=False
        def restore(*args):self.assertFalse(playing[0],'Never briefly unmute an ad while switching source')
        with patch.object(m,'target',return_value={'url':TRACK}),patch.object(m,'evaluate',side_effect=evaluate),patch.object(s,'ad_filter',side_effect=restore),patch.object(m,'open_browser'),patch.object(m,'install_volume_hook'),patch.object(m,'cdp'),patch.object(m,'status',return_value={}):
            m.select_source('youtube')


if __name__=='__main__':unittest.main()
