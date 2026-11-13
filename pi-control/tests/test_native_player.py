import copy
import json
import unittest
from unittest.mock import Mock,patch
import native_player as n

APP='org.mpris.MediaPlayer2.vlc'
OWNER=':1.123'
STATE=dict(id=APP,owner=OWNER,title='Song',artist='',playback='Paused',position=2,duration=30,volume=20,
           can_play=True,can_pause=True,can_next=True,can_previous=True,can_seek=True,can_volume=True,track='a')


class NativeTests(unittest.TestCase):
    def test_rejects_arbitrary_names_and_browser_targets(self):
        for value in ('org.freedesktop.DBus',APP+';touch','org.mpris.MediaPlayer2.chromium.instance1',None):
            with self.assertRaises(ValueError):n.valid(value)

    def test_duplicate_process_aliases_are_listed_once(self):
        def reply(destination,path,interface,method,*args):
            if method=='ListNames':return [[APP,APP+'.instance1','org.mpris.MediaPlayer2.chromium.instance2']]
            if method=='GetNameOwner':return [OWNER if args[-1]==APP else ':1.124']
            if method=='GetConnectionUnixProcessID':return [123]
            if method=='Get':return ['VLC']
            raise AssertionError(method)
        with patch.object(n,'bus',side_effect=reply):
            rows=n.NativePlayer().players()['players']
            self.assertEqual(rows,[dict(id=APP,owner=OWNER,label='VLC')])

    def test_stale_owner_rejected_before_any_mutation(self):
        app=n.NativePlayer()
        with patch.object(app,'owner',return_value=':1.999'),patch.object(n,'bus') as call:
            with self.assertRaises(ValueError):app.command(APP,OWNER,'play')
            call.assert_not_called()

    def test_status_exports_only_allowlisted_metadata(self):
        props=dict(Metadata={'xesam:title':'Song','xesam:artist':['Artist'],'xesam:url':'file:///private/file','private':'secret',
                             'mpris:length':30000000,'mpris:trackid':'/private/object'},Position=2000000,PlaybackStatus='Paused',
                   Volume=.2,CanControl=True,CanPlay=True)
        app=n.NativePlayer()
        with patch.object(app,'check'),patch.object(n,'bus',return_value=[props]) as call:
            result=app.status(APP,OWNER)
            call.assert_called_once_with(OWNER,n.PATH,n.PROPERTIES,'GetAll','s',n.PLAYER)
            self.assertEqual(result['title'],'Song');self.assertEqual(result['position'],2)
            self.assertNotIn('private',json.dumps(result));self.assertNotIn('secret',json.dumps(result))
            self.assertFalse(result['can_seek'])

    def test_commands_target_unique_owner_and_confirm_observed_state(self):
        app=n.NativePlayer();after=dict(STATE,playback='Playing')
        with patch.object(app,'snapshot',side_effect=[STATE,after]),patch.object(app,'check'),patch.object(n,'bus') as call:
            result=app.command(APP,OWNER,'play')
            call.assert_called_once_with(OWNER,n.PATH,n.PLAYER,'Play')
            self.assertEqual(result['receipt']['state'],'confirmed')

    def test_no_change_is_not_reported_as_confirmed(self):
        app=n.NativePlayer()
        with patch.object(app,'snapshot',return_value=copy.deepcopy(STATE)),patch.object(app,'check'),patch.object(n,'bus'),patch.object(n.time,'monotonic',side_effect=[0,2]):
            self.assertEqual(app.command(APP,OWNER,'play')['receipt']['state'],'unconfirmed')

    def test_capability_failure_never_writes(self):
        app=n.NativePlayer()
        with patch.object(app,'snapshot',return_value=dict(STATE,can_seek=False)),patch.object(n,'bus') as call:
            with self.assertRaises(ValueError):app.command(APP,OWNER,'seek',10)
            call.assert_not_called()

    def test_seek_receipt_requires_expected_direction_and_position(self):
        for position,expected in ((12,'confirmed'),(0,'unconfirmed')):
            app=n.NativePlayer()
            with patch.object(app,'snapshot',side_effect=[STATE,dict(STATE,position=position)]),patch.object(app,'check'),patch.object(n,'bus'),patch.object(n.time,'monotonic',side_effect=[0,2]):
                self.assertEqual(app.command(APP,OWNER,'seek',10)['receipt']['state'],expected)

    def test_strict_volume_seek_and_command_bounds(self):
        app=n.NativePlayer()
        with patch.object(n,'bus') as call:
            for action,value in [('volume',True),('volume',float('nan')),('volume',101),('volume',-1),('seek',True),('seek',12),('Quit',None)]:
                with self.assertRaises(ValueError):app.command(APP,OWNER,action,value)
            call.assert_not_called()

    def test_bus_transport_is_bounded_and_never_uses_shell(self):
        with patch.object(n.subprocess,'run',return_value=Mock(stdout='{"type":"s","data":["x"]}')) as command:
            self.assertEqual(n.bus(APP,n.PATH,n.PROPERTIES,'Get','ss','x','y'),['x'])
            kwargs=command.call_args.kwargs;self.assertNotIn('shell',kwargs);self.assertLess(kwargs['timeout'],2)
        with patch.object(n.subprocess,'run',return_value=Mock(stdout='x'*262145)):
            with self.assertRaises(ValueError):n.bus(APP,n.PATH,n.PROPERTIES,'Get')

    def test_owner_reply_must_be_a_unique_name(self):
        with patch.object(n,'bus',return_value=['invalid']):
            with self.assertRaises(ValueError):n.NativePlayer().owner(APP)
