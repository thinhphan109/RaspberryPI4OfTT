import json
import unittest
from unittest.mock import patch
import app
import robotvision


PAGE=b'<html><head><link href="/studio.css"><meta name="edgevision-csrf" content="abcdef"><script src="/studio-bridge.js"></script></head><body><script src="/vision.js"></script></body></html>'


class RobotVisionGatewayTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING']=True
        self.client=app.app.test_client()

    def authenticate(self):
        with self.client.session_transaction() as s:s['logged_in']=True;s['csrf']='session-token'

    def test_all_routes_need_login_and_login_returns_to_robotvision(self):
        for path in ('/robotvision/','/robotvision/vision.js','/robotvision/api/ai'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,302);self.assertIn('next=robotvision',response.location)
        with patch.object(app,'WEB_PASS','test-password'):
            response=self.client.post('/login?next=robotvision',data={'username':app.WEB_USER,'password':'test-password'})
        self.assertEqual(response.location,'/robotvision/')

    def test_html_token_is_session_scoped_assets_prefixed_permissions_explicit(self):
        self.authenticate()
        with patch.object(robotvision,'upstream',return_value=(200,PAGE,'text/html',None)):
            response=self.client.get('/robotvision/')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'content="session-token"',response.data);self.assertNotIn(b'content="abcdef"',response.data)
        self.assertIn(b'/robotvision/vision.js',response.data);self.assertIn(b'edgevision-base',response.data)
        self.assertEqual(response.headers['Permissions-Policy'],'camera=(self), microphone=()')
        self.assertIn('no-store',response.headers['Cache-Control'])
        with patch.object(robotvision,'upstream',return_value=(200,PAGE,'text/html',None)):
            self.assertEqual(self.client.get('/robotvision/',headers={'Sec-Fetch-Site':'cross-site'}).status_code,200)
            self.assertEqual(self.client.get('/robotvision/api/ai',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_path_allowlist_blocks_model_upload_robot_camera_and_traversal(self):
        self.authenticate()
        with patch.object(robotvision,'upstream') as upstream:
            for path,method in [('api/ai/import','post'),('api/studio/joints','post'),('api/camera','get'),('http:/example.com','get'),('..%2F..%2Fetc%2Fpasswd','get')]:
                response=getattr(self.client,method)('/robotvision/'+path,json={})
                self.assertEqual(response.status_code,404,path)
            upstream.assert_not_called()

    def test_csrf_origin_and_size_rejected_before_upstream(self):
        self.authenticate()
        with patch.object(robotvision,'upstream') as upstream:
            for headers in ({},{'X-EdgeVision-CSRF':'session-token','Origin':'https://other.invalid'},
                            {'X-EdgeVision-CSRF':'session-token','Sec-Fetch-Site':'cross-site'}):
                response=self.client.post('/robotvision/api/ai/stop',json={},headers=headers)
                self.assertEqual(response.status_code,403)
            response=self.client.post('/robotvision/api/ai/process',data=b'x'*(robotvision.LIMIT+1),content_type='image/jpeg',headers={'X-EdgeVision-CSRF':'session-token'})
            self.assertIn(response.status_code,(400,413));upstream.assert_not_called()

    def test_binary_frame_bypasses_only_legacy_64k_limit_and_forwards_no_cookie(self):
        self.authenticate();calls=[]
        def upstream(path,method='GET',body=None,headers=None):
            calls.append((path,method,body,headers))
            return (200,PAGE,'text/html',None) if path=='vision' else (200,b'{"result":{},"jpeg":""}','application/json',None)
        raw=b'x'*100000
        with patch.object(robotvision,'upstream',side_effect=upstream):
            response=self.client.post('/robotvision/api/ai/process',data=raw,content_type='image/jpeg',headers={'X-EdgeVision-CSRF':'session-token','X-AI-Source':'browser_camera'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(calls[-1][2],raw);self.assertEqual(calls[-1][3]['X-EdgeVision-CSRF'],'abcdef')
        self.assertNotIn('Cookie',calls[-1][3]);self.assertEqual(app.app.config['MAX_CONTENT_LENGTH'],65536)

    def test_busy_gate_and_invalid_queries_do_not_call_process(self):
        self.authenticate()
        robotvision._process.acquire()
        try:
            with patch.object(robotvision,'upstream',return_value=(200,PAGE,'text/html',None)) as upstream:
                r=self.client.post('/robotvision/api/ai/process',json={'viewer':'a'*32,'settings':{}},headers={'X-EdgeVision-CSRF':'session-token'})
                self.assertEqual(r.status_code,409);self.assertEqual(upstream.call_count,1)
        finally:robotvision._process.release()
        with patch.object(robotvision,'upstream') as upstream:
            self.assertEqual(self.client.get('/robotvision/api/ai?url=http://evil').status_code,400)
            self.assertEqual(self.client.get('/robotvision/api/ai/frame?id=../../secret').status_code,400)
            upstream.assert_not_called()


if __name__=='__main__':unittest.main()
