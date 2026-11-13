import unittest
from unittest.mock import patch
import media_agent as m
from spotify_player import AdStallGuard

AD=dict(connected=True,ad=True,paused=False,login_required=False,position_known=True,position=0,title='Advertisement',duration=30)


class SpotifyAdStallTests(unittest.TestCase):
    def test_only_explicit_stationary_ad_can_request_reload(self):
        g=AdStallGuard()
        self.assertFalse(g.observe(AD,now=0));self.assertFalse(g.observe(AD,now=104))
        self.assertTrue(g.observe(AD,now=105));self.assertEqual(g.summary()['attempts'],1)

    def test_progressing_ads_never_reload(self):
        g=AdStallGuard()
        for i in range(100):self.assertFalse(g.observe(dict(AD,position=i),now=i*5))

    def test_no_reload_for_music_pause_login_unknown_position_or_hold(self):
        for change in ({'ad':False},{'paused':True},{'paused':None},{'login_required':True},{'connected':False},{'position_known':False}):
            g=AdStallGuard();g.observe(AD,now=0)
            self.assertFalse(g.observe(dict(AD,**change),now=500))
            self.assertFalse(g.observe(AD,now=501),'Blocked time must not count as stalled time')
        g=AdStallGuard();g.observe(AD,now=0)
        self.assertFalse(g.observe(AD,blocked=True,now=500));self.assertFalse(g.observe(AD,now=501))

    def test_rate_limit_survives_episode_reset_and_failed_reload(self):
        g=AdStallGuard();g.observe(AD,now=0)
        self.assertTrue(g.observe(AD,now=105))
        g.reset();g.observe(AD,now=106)
        self.assertFalse(g.observe(AD,now=211))
        self.assertTrue(g.observe(AD,now=705))
        g.reset();g.observe(AD,now=800)
        self.assertFalse(g.observe(AD,now=2000));self.assertEqual(g.summary()['attempts'],2)
        self.assertTrue(g.observe(AD,now=3706))

    def test_manual_pause_does_not_reload_or_unpause(self):
        with patch.multiple(m,SPOTIFY_AD_GUARD=AdStallGuard(),MANUAL_PAUSE=True,SPOTIFY_PENDING=0),patch.object(m,'spotify_status',return_value=AD),patch.object(m,'volume_tick'),patch.object(m,'sleep_tick',return_value=False),patch.object(m,'cdp') as cdp,patch.object(m.spotify,'ad_filter'):
            m.spotify_tick();cdp.assert_not_called()

    def test_tick_reloads_current_page_without_navigation_or_credential_access(self):
        g=AdStallGuard()
        with patch.multiple(m,SPOTIFY_AD_GUARD=g,MANUAL_PAUSE=False,SPOTIFY_PENDING=0),patch.object(g,'observe',return_value=True),patch.object(m,'spotify_status',return_value=AD),patch.object(m,'volume_tick'),patch.object(m,'sleep_tick',return_value=False),patch.object(m,'cdp') as cdp,patch.object(m.spotify,'ad_filter') as mute:
            m.spotify_tick();cdp.assert_called_once_with('Page.reload',{'ignoreCache':False});mute.assert_not_called()
