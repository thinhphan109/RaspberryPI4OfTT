import unittest
from unittest.mock import patch
import app
import media_agent as m

class MediaTests(unittest.TestCase):
    def setUp(self):m.QUEUE.clear();m.NONSTOP=False;m.MANUAL_PAUSE=False
    def test_video_links_canonicalized(self):
        for u in ['https://youtu.be/abcdefghijk?t=3','https://music.youtube.com/watch?v=abcdefghijk&list=x','https://www.youtube.com/shorts/abcdefghijk']:
            self.assertEqual(m.youtube_url(u),'https://www.youtube.com/watch?v=abcdefghijk')
    def test_unsafe_links_rejected(self):
        for u in ['http://youtube.com/watch?v=abcdefghijk','https://youtube.com.evil/watch?v=abcdefghijk','file:///etc/passwd','https://user@youtube.com/watch?v=abcdefghijk','https://youtube.com:443/watch?v=abcdefghijk','https://youtube.com/results?q=x',None]:
            with self.subTest(u=u),self.assertRaises(ValueError):m.youtube_url(u)
    def test_queue_bounded_and_next_failure_preserves_item(self):
        with patch.object(m,'status',return_value={}):
            for i in range(50):m.dispatch({'action':'enqueue','url':'https://youtu.be/abcdefghijk'})
            with self.assertRaises(ValueError):m.dispatch({'action':'enqueue','url':'https://youtu.be/abcdefghijk'})
            with patch.object(m,'status',return_value={'up_next':dict(url=m.QUEUE[0],queue_index=0)}),patch.object(m,'play',side_effect=RuntimeError),self.assertRaises(RuntimeError):m.dispatch({'action':'next'})
            self.assertEqual(len(m.QUEUE),50)
    def test_numeric_and_unknown_commands_rejected(self):
        for payload in [{'action':'volume','value':float('nan')},{'action':'volume','value':True},{'action':'volume','value':101},{'action':'seek','value':500},{'action':'remove','index':-1},{'action':'javascript','value':'bad'}]:
            with self.subTest(payload=payload),self.assertRaises(ValueError):m.dispatch(payload)
    def test_auth_and_csrf_before_agent(self):
        c=app.app.test_client()
        self.assertEqual(c.get('/api/media').status_code,302)
        with c.session_transaction() as s:s['logged_in']=True;s['csrf']='media-test'
        with patch.object(app.media,'call') as call:
            self.assertEqual(c.post('/api/media',json={'action':'next'}).status_code,403);call.assert_not_called()
            call.return_value={'connected':False}
            self.assertEqual(c.get('/api/media').json['data']['connected'],False)
            self.assertEqual(c.post('/api/media',json={'action':'clear'},headers={'X-CSRF-Token':'media-test'}).status_code,200)

    def test_cdp_session_persists_for_new_document_volume_hook(self):
        import json
        from unittest.mock import MagicMock
        fake=MagicMock()
        fake.recv.side_effect=lambda:json.dumps({'id':json.loads(fake.send.call_args.args[0])['id'],'result':{}})
        m.WS=None;m.WS_TARGET=None
        try:
            with patch.object(m,'target',return_value={'id':'page','webSocketDebuggerUrl':'ws://127.0.0.1:18769/devtools/page/page'}),patch.object(m.websocket,'create_connection',return_value=fake) as connect:
                m.cdp('Page.addScriptToEvaluateOnNewDocument',{'source':'/* test */'})
                m.cdp('Page.navigate',{'url':'https://www.youtube.com/'})
                self.assertEqual(connect.call_count,1)
                fake.close.assert_not_called()
        finally:m.WS=None;m.WS_TARGET=None

if __name__=='__main__':unittest.main()
