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
            page=Mock();page.call.side_effect=lambda method,params=None: {'result':{'value':{'rows':[dict(url='https://youtu.be/abcdefghijk',title='Music')]}}} if method=='Runtime.evaluate' else {}
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
                return {'result':{'value':{'rows':[dict(url='https://youtu.be/abcdefghijk',title='Music')]}}}
            page.call.side_effect=call
            with patch.object(cat,'recover'),patch.object(cat,'browser',return_value=browser),patch.object(c,'Connection',return_value=page):
                cat.worker('youtube','music','https://www.youtube.com/results?search_query=music')
            self.assertEqual(len(cat.status()['rows']),1);self.assertGreaterEqual(len(attempts),2);self.assertFalse(cat.owned)


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
    def test_cross_provider_selection_navigates_once(self):
        from media_policy import PlaybackPolicy
        with tempfile.TemporaryDirectory() as folder,patch.multiple(m,PROVIDER='youtube',STANDBY=False,MANUAL_PAUSE=False,SPOTIFY_PENDING=0,SPOTIFY_URL='https://open.spotify.com/',CONFIG=Path(folder)/'config.json',POLICY=PlaybackPolicy(),WAKE_URL=''),patch.object(m,'player_status',return_value={}),patch.object(m,'status',return_value={}),patch.object(m,'evaluate',return_value=True),patch.object(m,'install_volume_hook'),patch.object(m,'cdp') as cdp,patch.object(m.BT_GUARD,'latched',False):
            url='https://open.spotify.com/playlist/'+'A'*22
            m.play_destination('spotify',url)
            cdp.assert_called_once_with('Page.navigate',{'url':url})

    def test_cold_selection_waits_for_readiness_instead_of_navigating_early(self):
        with patch.multiple(m,PROVIDER='youtube',STANDBY=True,MANUAL_PAUSE=True,SPOTIFY_URL='https://open.spotify.com/',WAKE_URL='',WAKE_UNTIL=0),patch.object(m,'player_status',return_value={}),patch.object(m,'status',return_value={}),patch.object(m,'set_power') as power,patch.object(m,'cdp') as cdp,patch.object(m.BT_GUARD,'latched',False):
            url='https://open.spotify.com/playlist/'+'A'*22
            m.play_destination('spotify',url)
            power.assert_called_once_with(True);cdp.assert_not_called()
            self.assertEqual(m.WAKE_URL,url);self.assertFalse(m.MANUAL_PAUSE)
