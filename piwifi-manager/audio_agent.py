"""User-session audio daemon; independent of Media/browser lifetime."""
import json
import os
import socketserver
from runtime_config import desktop_runtime
import audio_control


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(12)
        try:
            raw=self.rfile.readline(4097)
            if len(raw)>4096:raise ValueError('Yêu cầu âm thanh quá dài')
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('Yêu cầu âm thanh không hợp lệ')
            result={'ok':True,'data':audio_control.dispatch(data)}
        except Exception as error:result={'ok':False,'error':str(error)[:200]}
        self.wfile.write(json.dumps(result).encode()+b'\n')


def main():
    path=desktop_runtime()/'pi-audio.sock'
    if path.is_symlink() or path.exists() and not path.is_socket():raise ValueError('Unsafe audio socket')
    path.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(str(path),Handler) as server:
        os.chmod(path,0o600)
        try:server.serve_forever()
        finally:path.unlink(missing_ok=True)


if __name__=='__main__':main()
