import io
import unittest
from unittest.mock import Mock,patch
import app as web
import media_agent as agent


class NativeIntegrationTests(unittest.TestCase):
    def test_native_requests_do_not_take_browser_policy_lock(self):
        handler=object.__new__(agent.Handler)
        handler.connection=Mock();handler.rfile=io.BytesIO(b'{"action":"apps"}\n');handler.wfile=io.BytesIO()
        with patch.object(agent,'native_dispatch',return_value={'players':[]}) as native,patch.object(agent,'LOCK') as lock:
            agent.Handler.handle(handler)
            native.assert_called_once_with({'action':'apps'});lock.__enter__.assert_not_called()
        self.assertIn(b'"ok": true',handler.wfile.getvalue())

    def test_app_api_requires_auth_and_csrf_before_dispatch(self):
        client=web.app.test_client()
        with patch.object(web.media,'call',return_value={'players':[]}) as call:
            self.assertEqual(client.post('/api/media',json={'action':'apps'}).status_code,302)
            with client.session_transaction() as session:session.update(logged_in=True,csrf='native-test')
            self.assertEqual(client.post('/api/media',json={'action':'apps'}).status_code,403)
            call.assert_not_called()
            response=client.post('/api/media',json={'action':'apps'},headers={'X-CSRF-Token':'native-test'})
            self.assertEqual(response.status_code,200);call.assert_called_once_with({'action':'apps'})

    def test_dispatch_preserves_exact_selected_instance_and_command(self):
        payload=dict(action='app_command',id='org.mpris.MediaPlayer2.vlc',owner=':1.42',command='seek',value=-10)
        with patch.object(agent.NATIVE,'command',return_value={'receipt':{'state':'confirmed'}}) as command:
            agent.native_dispatch(payload)
            command.assert_called_once_with(payload['id'],payload['owner'],'seek',-10)
