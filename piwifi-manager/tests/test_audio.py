import unittest
from unittest.mock import patch
import audio_control as a
import app

NODE=dict(id=57,name='alsa_output.test',label='Speaker',kind='output')

class AudioTests(unittest.TestCase):
    def test_auth_csrf(self):
        client=app.app.test_client();self.assertEqual(client.get('/api/audio').status_code,302)
        with client.session_transaction() as session:session['logged_in']=True;session['csrf']='audio-test'
        with patch.object(app.media,'call',return_value={}) as call:
            self.assertEqual(client.post('/api/audio',json=dict(action='power',enabled=True)).status_code,403);call.assert_not_called()
            self.assertEqual(client.get('/api/audio').status_code,200)
            call.assert_called_with(dict(action='audio',payload=dict(action='status')))
            self.assertEqual(client.post('/api/audio',json=dict(action='status'),headers={'X-CSRF-Token':'audio-test'}).status_code,200)

    def test_reject_arbitrary_command_and_arguments(self):
        for payload in [dict(action='shell'),dict(action='connect',address=';reboot'),dict(action='pair',address='AA:BB'),dict(action='power',enabled=1),dict(action='volume',id='57',kind='output',value=20)]:
            with self.subTest(payload=payload),self.assertRaises(ValueError):a.dispatch(payload)

    def test_only_live_node_can_be_modified(self):
        with patch.object(a,'nodes',return_value=[NODE]),patch.object(a,'run') as run:
            with self.assertRaises(ValueError):a.dispatch(dict(action='volume',id=90,kind='output',value=30))
            run.assert_not_called()

    def test_volume_bounds_and_fixed_args(self):
        with patch.object(a,'nodes',return_value=[NODE]),patch.object(a,'run') as run,patch.object(a,'status',return_value={}):
            for value in [True,-1,101,float('nan')]:
                with self.subTest(value=value),self.assertRaises(ValueError):a.dispatch(dict(action='volume',id=57,kind='output',value=value))
            run.assert_not_called()
            a.dispatch(dict(action='volume',id=57,kind='output',value=25));run.assert_called_once_with(['wpctl','set-volume','57','0.25'])

    def test_default_keeps_easyeffects_following_physical_output(self):
        with patch.object(a,'nodes',return_value=[NODE]),patch.object(a,'run') as run,patch.object(a,'status',return_value={}):
            a.dispatch(dict(action='default',id=57,kind='output'))
            self.assertEqual(run.call_args_list[0].args[0],['wpctl','set-default','57'])
            self.assertEqual(run.call_args_list[1].args[0],['gsettings','set','com.github.wwmm.easyeffects.streamoutputs','use-default-output-device','true'])

    def test_virtual_devices_hidden(self):
        import json
        raw=[dict(id=57,info=dict(props={'media.class':'Audio/Sink','node.name':'alsa_output.test'})),dict(id=90,info=dict(props={'media.class':'Audio/Sink','node.name':'easyeffects_sink'})),dict(id=92,info=dict(props={'media.class':'Audio/Source','node.name':'easyeffects_source'}))]
        with patch.object(a,'run',return_value=json.dumps(raw)):self.assertEqual([n['id'] for n in a.nodes()],[57])

    def test_scan_is_bounded_and_always_stopped(self):
        with patch.object(a,'run',side_effect=[ValueError('failed'), '']) as run:
            a.background('scan');self.assertEqual(run.call_args_list[-1].args[0],['bluetoothctl','scan','off'])
            self.assertFalse(a.JOB['running'])

    def test_pair_does_not_implicitly_trust(self):
        with patch.object(a,'run',return_value='Pairing successful') as run:
            a.background('pair','AA:BB:CC:DD:EE:FF')
            self.assertEqual(run.call_count,1);self.assertNotIn('trust',run.call_args.args[0])

    def test_scan_already_stopped_is_success(self):
        with patch.object(a,'run',side_effect=['',ValueError('already stopped'),'Discovering: no']):
            a.background('scan');self.assertIn('hoàn tất',a.JOB['message']);self.assertFalse(a.JOB['running'])

if __name__=='__main__':unittest.main()
