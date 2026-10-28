"""Private standalone audio agent client, with legacy Media compatibility."""
import json
import socket
from runtime_config import desktop_runtime, modular


def call(payload, timeout=12):
    if not modular():
        import media
        return media.call({'action':'audio','payload':payload})
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout)
        client.connect(str(desktop_runtime()/'pi-audio.sock'))
        client.sendall(json.dumps(payload).encode()+b'\n')
        data=client.makefile('rb').readline(262145)
        if not data or len(data)>262144:raise RuntimeError('Invalid audio response')
        result=json.loads(data)
    if not result.get('ok'):raise ValueError(result.get('error','Audio unavailable'))
    return result['data']
