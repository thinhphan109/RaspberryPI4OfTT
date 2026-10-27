"""Authenticated dashboard client for a private, same-user media agent."""
import json
import os
import socket
from runtime_config import desktop_runtime

def call(payload):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(12)
        client.connect(str(desktop_runtime()/'pi-media.sock'))
        client.sendall(json.dumps(payload).encode()+b'\n')
        data=b''
        while not data.endswith(b'\n'):
            chunk=client.recv(65536)
            if not chunk or len(data)>262144:raise RuntimeError('Media agent response invalid')
            data+=chunk
    result=json.loads(data)
    if not result['ok']:raise ValueError(result['error'])
    return result['data']
