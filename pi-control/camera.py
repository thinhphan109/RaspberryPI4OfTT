"""Bounded client for the private camera socket. No public camera port."""
import json
import os
import socket
from runtime_config import desktop_runtime


def call(payload):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(8)
        client.connect(os.environ.get('PI_CAMERA_SOCKET', str(desktop_runtime()/'pi-camera.sock')))
        client.sendall(json.dumps(payload).encode()+b'\n')
        data = bytearray()
        while not data.endswith(b'\n'):
            chunk = client.recv(65536)
            if not chunk or len(data)+len(chunk) > 3*1024*1024:
                raise RuntimeError('Phản hồi camera không hợp lệ')
            data.extend(chunk)
    result = json.loads(data)
    if not result['ok']:
        raise ValueError(result['error'])
    return result['data']
