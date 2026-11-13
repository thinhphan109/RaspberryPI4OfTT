"""Bounded authenticated gateway to the private EdgeVision AI service only."""
import hmac
import json
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

BASE='http://127.0.0.1:18768'
PREFIX='/robotvision'
READ={'vision','vision.js','vision.css','studio.css','studio-bridge.js','fonts/noto-sans.woff2',
      'api/ai','api/ai/frame','api/ai/preview','api/ai/export'}
WRITE={'api/ai/activate','api/ai/stop','api/ai/camera','api/ai/process','api/ai/mapping'}
LIMIT=3*1024*1024
_process=threading.BoundedSemaphore(1)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def upstream(path,method='GET',body=None,headers=None):
    opener=build_opener(ProxyHandler({}),NoRedirect())
    request=Request(BASE+'/'+path,data=body,headers=headers or {},method=method)
    try:
        response=opener.open(request,timeout=35 if path=='api/ai/process' else 5)
    except HTTPError as exc:response=exc
    with response:
        raw=response.read(4_500_001)
        if len(raw)>4_500_000:raise ValueError('Phản hồi RobotVision vượt giới hạn.')
        return response.status,raw,response.headers.get('Content-Type','application/json'),response.headers.get('Content-Disposition')


def render_page(raw,csrf):
    text=raw.decode('utf-8')
    # Do not expose the loopback service's global token to public clients.
    text,count=re.subn(r'(<meta name="edgevision-csrf" content=")[a-f0-9]+(">)',lambda m:m[1]+csrf+m[2],text)
    if count!=1:raise ValueError('RobotVision chưa có giao diện tương thích.')
    for path in ('/studio.css','/vision.css','/vision.js','/studio-bridge.js','/vision'):
        text=text.replace('"'+path+'"','"'+PREFIX+path+'"')
    text=text.replace('</head>',f'<meta name="edgevision-base" content="{PREFIX}"><meta name="edgevision-public" content="1"></head>')
    return text.encode()


def proxy(request,session,Response):
    """Caller already enforces Pi Control login. No arbitrary upstream paths."""
    path=request.view_args.get('path','') or 'vision'
    if path not in (WRITE if request.method=='POST' else READ):
        return Response(json.dumps({'error':'Không hỗ trợ chức năng này trên trang demo.'}),status=404,mimetype='application/json')
    try:
        if request.headers.get('Sec-Fetch-Site')=='cross-site' and (request.method!='GET' or path!='vision'):
            raise PermissionError('Nguồn yêu cầu không hợp lệ.')
        if request.method=='POST':
            supplied=request.headers.get('X-EdgeVision-CSRF','')
            if not supplied or not hmac.compare_digest(supplied,session.get('csrf','')):raise PermissionError('Phiên đã đổi. Đăng nhập hoặc tải lại trang.')
            origin=request.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=request.host:raise PermissionError('Nguồn yêu cầu không hợp lệ.')
            if not request.content_length or request.content_length>LIMIT:raise ValueError('Ảnh JPEG tối đa 3 MiB.')
            if request.headers.get('Transfer-Encoding'):raise ValueError('Cần xác định kích thước ảnh.')
        query={}
        allowed={'id'} if path in ('api/ai/frame','api/ai/export') else {'viewer'} if path=='api/ai/preview' else set()
        if set(request.args)-allowed:raise ValueError('Tham số không hợp lệ.')
        for key in allowed:
            value=request.args.get(key,'')
            if not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('Phiên hoặc kết quả không hợp lệ.')
            query[key]=value
        target=path+('?' + urlencode(query) if query else '')
        headers={}
        body=None
        if request.method=='POST':
            kind=request.mimetype
            if path=='api/ai/process' and kind=='image/jpeg':
                body=request.get_data();headers['Content-Type']='image/jpeg'
                headers['X-AI-Options']=request.headers.get('X-AI-Options','{}')
                headers['X-AI-Source']=request.headers.get('X-AI-Source','uploaded_image')
                if len(headers['X-AI-Options'])>2048:raise ValueError('Cài đặt ảnh quá dài.')
            else:
                if request.content_length>16384:raise ValueError('Yêu cầu quá dài.')
                data=request.get_json(silent=True)
                if not isinstance(data,dict):raise ValueError('Yêu cầu JSON không hợp lệ.')
                body=json.dumps(data).encode();headers['Content-Type']='application/json'
            status,page,_,_=upstream('vision')
            if status!=200:raise ValueError('RobotVision chưa sẵn sàng.')
            match=re.search(rb'name="edgevision-csrf" content="([a-f0-9]+)"',page)
            if not match:raise ValueError('RobotVision chưa có phiên điều khiển.')
            headers['X-EdgeVision-CSRF']=match[1].decode()
        acquired=False
        try:
            if path=='api/ai/process':
                acquired=_process.acquire(blocking=False)
                if not acquired:return Response(json.dumps({'error':'AI đang xử lý một ảnh khác. Thử lại sau.'}),status=409,mimetype='application/json')
            status,raw,kind,disposition=upstream(target,request.method,body,headers)
        finally:
            if acquired:_process.release()
        if path=='vision' and status==200:raw=render_page(raw,session['csrf'])
        if path=='studio.css' and status==200:raw=raw.replace(b"'/fonts/",b"'/robotvision/fonts/")
        response=Response(raw,status=status,content_type=kind)
        response.headers.update({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
                                 'X-Frame-Options':'DENY','Permissions-Policy':'camera=(self), microphone=()',
                                 'Referrer-Policy':'same-origin',
                                 'Content-Security-Policy':"default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"})
        if disposition and path=='api/ai/export':response.headers['Content-Disposition']=disposition
        return response
    except PermissionError as exc:return Response(json.dumps({'error':str(exc)},ensure_ascii=False),status=403,mimetype='application/json')
    except ValueError as exc:return Response(json.dumps({'error':str(exc)},ensure_ascii=False),status=400,mimetype='application/json')
    except (OSError,URLError):return Response(json.dumps({'error':'RobotVision chưa kết nối. Kiểm tra service trên Pi.'}),status=503,mimetype='application/json')
