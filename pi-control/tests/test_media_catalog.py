import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import media_catalog as c
import media_agent as m
import audio_control as a


class CatalogTests(unittest.TestCase):
    def test_query_cannot_choose_host_or_inject_parameters(self):
        value, url=c.query('spotify','  test / & token=foo  ')
        self.assertEqual(value,'test / & token=foo')
        self.assertTrue(url.startswith('https://open.spotify.com/search/test%20%2F'))
        for provider,text in [('other','music'),('spotify',''),('youtube','a\nb'),('spotify','x'*121)]:
            with self.assertRaises(ValueError):c.query(provider,text)

    def test_results_restrict_urls_deduplicate_and_bound(self):
        good='https://open.spotify.com/track/'+'A'*22
        rows=c.results('spotify',dict(rows=[dict(url='https://evil.example/track/'+'B'*22,title='bad'),dict(url=good+'?tracking=1',title='<script>'),dict(url=good,title='duplicate')]))
        self.assertEqual(rows,[dict(url=good,title='<script>',subtitle='',provider='spotify')])
        many=[dict(url='https://www.youtube.com/watch?v='+str(i).zfill(11),title=str(i)) for i in range(40)]
        self.assertEqual(len(c.results('youtube',dict(rows=many))),12)

    def test_search_pages_never_become_playback_target(self):
        rows=[dict(id='search',url='https://open.spotify.com/search/music'),dict(id='main',url='https://open.spotify.com/playlist/'+'A'*22)]
        with patch.object(m,'pages',return_value=rows),patch.object(m,'PROVIDER','spotify'):
            self.assertEqual(m.target()['id'],'main')
        with patch.object(m,'pages',return_value=rows[:1]),self.assertRaises(ValueError):m.target()

    def test_worker_closes_owned_tab_and_caches_without_navigation_of_main(self):
        with tempfile.TemporaryDirectory() as folder:
            cat=c.Catalog(Path(folder)/'target.json')
            browser=Mock();browser.call.side_effect=[{'targetId':'temporary'}, {'success':True}]
            page=Mock();page.call.side_effect=lambda method,params=None: {'result':{'value':{'ready':True,'query':'music','rows':[dict(url='https://youtu.be/abcdefghijk',title='Music')]}}} if method=='Runtime.evaluate' else {}
            with patch.object(cat,'recover'),patch.object(cat,'browser',return_value=browser),patch.object(c,'Connection',return_value=page):
                cat.worker('youtube','music','https://www.youtube.com/results?search_query=music')
            self.assertFalse(cat.status()['running']);self.assertEqual(len(cat.status()['rows']),1)
            self.assertEqual(browser.call.call_args.args,('Target.closeTarget',{'targetId':'temporary'}))
            self.assertFalse(cat.ledger.exists());self.assertFalse(cat.owned)
            with patch.object(c.threading,'Thread') as thread:
                self.assertFalse(cat.start('youtube','music')['running']);thread.assert_not_called()

    def test_worker_failure_still_closes_tab_and_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            cat=c.Catalog(Path(folder)/'target.json');browser=Mock();browser.call.side_effect=[{'targetId':'temporary'},{'success':True}]
            with patch.object(cat,'recover'),patch.object(cat,'browser',return_value=browser),patch.object(c,'Connection',side_effect=ValueError('unavailable')):
                cat.worker('spotify','music','https://open.spotify.com/search/music')
            self.assertFalse(cat.status()['running']);self.assertTrue(cat.status()['message']);self.assertFalse(cat.ledger.exists())

    def test_busy_cold_renderer_can_recover_within_same_search_job(self):
        with tempfile.TemporaryDirectory() as folder:
            cat=c.Catalog(Path(folder)/'target.json');browser=Mock();browser.call.side_effect=[{'targetId':'temporary'},{'success':True}]
            page=Mock();attempts=[]
            def call(method,params=None):
                if method!='Runtime.evaluate':return {}
                attempts.append(1)
                if len(attempts)==1:raise c.websocket.WebSocketTimeoutException('busy')
                return {'result':{'value':{'ready':True,'query':'music','rows':[dict(url='https://youtu.be/abcdefghijk',title='Music')]}}}
            page.call.side_effect=call
            with patch.object(cat,'recover'),patch.object(cat,'browser',return_value=browser),patch.object(c,'Connection',return_value=page):
                cat.worker('youtube','music','https://www.youtube.com/results?search_query=music')
            self.assertEqual(len(cat.status()['rows']),1);self.assertGreaterEqual(len(attempts),2);self.assertFalse(cat.owned)

    def test_loading_or_wrong_query_is_not_a_completed_search(self):
        for raw in ({'rows':[{'title':'Footer'}]},dict(ready=False,query='music',kind='tracks'),dict(ready=True,query='previous',kind='tracks'),dict(ready=True,query='music',kind='playlists')):
            self.assertFalse(c.search_ready('spotify','music','tracks',raw))
        self.assertTrue(c.search_ready('spotify','music','tracks',dict(ready=True,query='music',kind='tracks')))

    def test_pasted_link_infers_provider_and_preserves_supported_context(self):
        from media_extras import link_destination
        self.assertEqual(link_destination('https://youtu.be/abcdefghijk?si=tracking'),('youtube','https://www.youtube.com/watch?v=abcdefghijk'))
        ident='A'*22
        self.assertEqual(link_destination('https://open.spotify.com/intl-vi/track/'+ident+'?si=tracking'),('spotify','https://open.spotify.com/track/'+ident))
        self.assertEqual(link_destination('spotify:track:'+ident),('spotify','https://open.spotify.com/track/'+ident))
        with patch.object(m,'PROVIDER','spotify'),patch.object(m,'play_destination',return_value={}) as launch:
            m.run_command(dict(action='play',url='https://youtu.be/abcdefghijk'))
            launch.assert_called_once_with('youtube','https://www.youtube.com/watch?v=abcdefghijk')

    def test_explicit_search_wakes_quietly_and_invalid_query_does_not_wake(self):
        with patch.multiple(m,STANDBY=True,MANUAL_PAUSE=False,WAKE_URL='old',SPOTIFY_PENDING=9,YOUTUBE_PENDING=('old',9)),patch.object(m,'open_browser') as browser,patch.object(m,'save_nonstop'),patch.object(m.CATALOG,'start',return_value={}):
            with self.assertRaises(ValueError):m.run_command(dict(action='catalog_search',provider='spotify',query=''))
            browser.assert_not_called()
            m.run_command(dict(action='catalog_search',provider='spotify',query='music'))
            browser.assert_called_once();self.assertFalse(m.STANDBY);self.assertTrue(m.MANUAL_PAUSE);self.assertFalse(m.WAKE_URL)

    def test_song_receipt_requires_actual_track_instead_of_only_page_navigation(self):
        from media_extras import CommandReceipt
        wanted='https://open.spotify.com/track/'+'A'*22
        receipt=CommandReceipt();receipt.begin('play',{},dict(provider='spotify',url=wanted),now=0)
        current=dict(provider='spotify',connected=True,has_video=True,paused=False,context_url=wanted,url='https://open.spotify.com/track/'+'B'*22)
        self.assertEqual(receipt.observe(current,now=1)['state'],'pending')
        current['url']=wanted;self.assertEqual(receipt.observe(current,now=2)['state'],'pending')
        current['track_matches']=True;self.assertEqual(receipt.observe(current,now=3)['state'],'confirmed')

    def test_unavailable_spotify_content_is_reported_before_timeout(self):
        import spotify_player
        from media_extras import CommandReceipt
        state=spotify_player.state(dict(content_unavailable=True,has_video=True,can_toggle=True,url='https://open.spotify.com/playlist/'+'A'*22))
        self.assertFalse(state['has_video']);self.assertFalse(state['can_toggle']);self.assertTrue(state['notice'])
        receipt=CommandReceipt();receipt.begin('play',{},dict(provider='spotify',url=state['url']),now=0)
        self.assertEqual(receipt.observe(state,now=1)['state'],'unconfirmed')


class QuickOutputTests(unittest.TestCase):
    def test_rerouted_or_reused_node_is_never_modified(self):
        item=dict(id=57,kind='output',name='bluez_output.test',label='Speaker')
        with patch.object(a,'nodes',return_value=[item]),patch.object(a,'default_name',return_value='alsa_output.other'),patch.object(a,'run') as run:
            with self.assertRaises(ValueError):a.dispatch(dict(action='output_volume',id=57,name=item['name'],value=25))
            run.assert_not_called()
        with patch.object(a,'nodes',return_value=[item]),patch.object(a,'default_name',return_value=item['name']),patch.object(a,'run') as run:
            with self.assertRaises(ValueError):a.dispatch(dict(action='output_mute',id=57,name='old_node',muted=True))
            run.assert_not_called()

    def test_quick_read_does_not_scan_bluetooth_and_write_has_strict_bounds(self):
        item=dict(id=57,kind='output',name='bluez_output.test',label='Speaker')
        with patch.object(a,'nodes',return_value=[item]),patch.object(a,'default_name',return_value=item['name']),patch.object(a,'run',return_value='Volume: 0.25'),patch.object(a,'bluetooth') as bluetooth:
            self.assertEqual(a.output_status()['output']['volume'],25);bluetooth.assert_not_called()
        with patch.object(a,'nodes',return_value=[item]),patch.object(a,'default_name',return_value=item['name']),patch.object(a,'run') as run,patch.object(a,'output_status',return_value={}):
            for value in [True,-1,101,float('nan')]:
                with self.assertRaises(ValueError):a.dispatch(dict(action='output_volume',id=57,name=item['name'],value=value))
            run.assert_not_called()
            a.dispatch(dict(action='output_volume',id=57,name=item['name'],value=25))
            run.assert_called_once_with(['wpctl','set-volume','57','0.25'])


class LaunchTests(unittest.TestCase):
    def setUp(self):
        metadata=patch.object(m.spotify,'track_metadata',return_value=None);metadata.start();self.addCleanup(metadata.stop)
    def test_cold_chromium_newtab_is_eligible_but_search_and_settings_are_not(self):
        with patch.object(m,'PROVIDER','spotify'),patch.object(m,'pages',return_value=[dict(id='search',url='https://open.spotify.com/search/test/tracks'),dict(id='settings',url='chrome://settings/'),dict(id='empty',url='chrome://newtab/')]):
            self.assertEqual(m.target()['id'],'empty')
    def test_unavailable_content_clears_launch_pending_without_clicking_play(self):
        with patch.object(m,'SPOTIFY_PENDING',m.time.monotonic()+45),patch.object(m,'spotify_status',return_value=dict(connected=True,content_unavailable=True)),patch.object(m.spotify,'activate') as activate:
            m.spotify_tick();self.assertEqual(m.SPOTIFY_PENDING,0);activate.assert_not_called()
    def test_rest_does_not_save_unknown_spotify_volume_as_zero_or_lose_playlist(self):
        import json
        track='https://open.spotify.com/track/'+'A'*22;playlist='https://open.spotify.com/playlist/'+'B'*22
        with tempfile.TemporaryDirectory() as folder,patch.multiple(m,PROVIDER='spotify',STANDBY=False,VOLUME=52,SPOTIFY_URL=playlist,CONFIG=Path(folder)/'config.json',WAKE_URL=''),patch.object(m,'status',return_value=dict(url=track,context_url=playlist,has_video=True,volume=0,can_volume=False)),patch.object(m.subprocess,'run'):
            m.set_power(False)
            saved=json.loads(m.CONFIG.read_text());self.assertEqual(saved['volume'],52);self.assertEqual(saved['spotify_url'],playlist)

    def test_cross_provider_selection_navigates_once(self):
        from media_policy import PlaybackPolicy
        with tempfile.TemporaryDirectory() as folder,patch.multiple(m,PROVIDER='youtube',STANDBY=False,MANUAL_PAUSE=False,SPOTIFY_PENDING=0,SPOTIFY_URL='https://open.spotify.com/',CONFIG=Path(folder)/'config.json',POLICY=PlaybackPolicy(),WAKE_URL=''),patch.object(m,'player_status',return_value={}),patch.object(m,'status',return_value={}),patch.object(m,'evaluate',return_value=True),patch.object(m,'install_volume_hook'),patch.object(m,'cdp') as cdp,patch.object(m.BT_GUARD,'latched',False):
            url='https://open.spotify.com/playlist/'+'A'*22
            m.play_destination('spotify',url)
            cdp.assert_not_called();self.assertEqual(m.WAKE_URL,url)
            m.resume_tick()
            cdp.assert_called_once_with('Page.navigate',{'url':url})
            self.assertEqual(m.SPOTIFY_URL,url);self.assertGreater(m.SPOTIFY_PENDING,0)
            self.assertEqual(__import__('json').loads(m.CONFIG.read_text())['spotify_url'],url)

    def test_cold_selection_waits_for_readiness_instead_of_navigating_early(self):
        with patch.multiple(m,PROVIDER='youtube',STANDBY=True,MANUAL_PAUSE=True,SPOTIFY_URL='https://open.spotify.com/',WAKE_URL='',WAKE_UNTIL=0),patch.object(m,'player_status',return_value={}),patch.object(m,'status',return_value={}),patch.object(m,'set_power') as power,patch.object(m,'cdp') as cdp,patch.object(m.BT_GUARD,'latched',False):
            url='https://open.spotify.com/playlist/'+'A'*22
            m.play_destination('spotify',url)
            power.assert_called_once_with(True);cdp.assert_not_called()
            self.assertEqual(m.WAKE_URL,url);self.assertFalse(m.MANUAL_PAUSE)


class PublicSpotifyMetadataTests(unittest.TestCase):
    def test_album_highlight_preserves_track_identity_and_rejects_foreign_origin(self):
        import spotify_player as s
        track='https://open.spotify.com/track/'+'A'*22
        album='https://open.spotify.com/album/'+'B'*22+'?highlight=spotify%3Atrack%3A'+'A'*22+'&autoplay_ok=1'
        self.assertEqual(s.public_destination(album),track)
        with self.assertRaises(ValueError):s.public_destination(album.replace('open.spotify.com','evil.example'))

    def test_oembed_is_bounded_cached_and_cannot_choose_another_host(self):
        import json,spotify_player as s
        target='https://open.spotify.com/track/'+'Z'*22
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(dict(title='Selected song',thumbnail_url='https://i.scdn.co/image/'+'a'*40,html='MUST NOT RUN')).encode()
        with patch.object(s,'TRACK_METADATA',{}),patch.object(s.HTTP,'open',return_value=response) as request:
            self.assertEqual(s.track_metadata(target)['title'],'Selected song');s.track_metadata(target)
            request.assert_called_once();self.assertTrue(request.call_args.args[0].startswith('https://open.spotify.com/oembed?'))
            response.read.assert_called_once_with(65537)
            with self.assertRaises(ValueError):s.track_metadata('https://evil.example/track/'+'Z'*22)
