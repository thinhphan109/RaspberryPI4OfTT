"""Read-only MCP stdio over the existing SSH key; stdout is JSON-RPC only."""
import json
import subprocess
import sys
from observer import current, events, history
from state import read

NAMES = {
    'pi_metrics': 'Đọc sức khỏe Pi, tài nguyên, tiến trình và chẩn đoán mạng gần nhất.',
    'pi_network': 'Đọc trạng thái Wi-Fi; không đọc mật khẩu.',
    'pi_history': 'Đọc lịch sử tài nguyên 24 giờ gần nhất.',
    'pi_events': 'Đọc lịch sử sự kiện gần nhất.',
    'pi_deployments': 'Đọc phiên bản và danh sách bản sao lưu triển khai.',
    'pi_operation': 'Đọc tiến trình đổi mạng hiện tại.',
}

def call(name):
    if name == 'pi_metrics': return current()
    if name == 'pi_history': return history()
    if name == 'pi_events': return events()
    if name == 'pi_operation': return read('operation.json', {})
    if name in ('pi_network', 'pi_deployments'):
        action = 'status' if name == 'pi_network' else 'deployments'
        p = subprocess.run(['/usr/bin/sudo', '/usr/local/sbin/piwifi-helper', action],
                           capture_output=True, text=True, timeout=35)
        payload = json.loads(p.stdout)
        if not payload.get('ok'): raise RuntimeError(payload.get('error', 'Helper failed'))
        return payload['data']
    raise ValueError('Unknown read-only tool')

def respond(message):
    if not isinstance(message, dict):
        return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request'}}
    method = message.get('method')
    if 'id' not in message: return None
    result = {}
    if method == 'initialize':
        version = message.get('params', {}).get('protocolVersion')
        supported = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
        result = dict(protocolVersion=version if version in supported else '2025-06-18',
                      capabilities={'tools': {}}, serverInfo={'name': 'raspberry-pi-readonly', 'version': '3.1.0'})
    elif method == 'tools/list':
        result = {'tools': [dict(name=n, description=d, inputSchema={'type':'object','properties':{},'additionalProperties':False},
                                annotations={'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False})
                            for n, d in sorted(NAMES.items())]}
    elif method == 'tools/call':
        try:
            params = message.get('params', {})
            if params.get('arguments', {}): raise ValueError('Tools do not accept arguments')
            data = call(params.get('name'))
            result = {'content': [{'type':'text','text':json.dumps(data, ensure_ascii=False)}], 'isError':False}
        except Exception as exc:
            result = {'content':[{'type':'text','text':str(exc)}], 'isError':True}
    elif method != 'ping':
        return {'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':message['id'],'result':result}

def main():
    for line in sys.stdin:
        try:
            reply = respond(json.loads(line))
        except (ValueError, TypeError):
            reply = {'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}}
        if reply is not None:
            print(json.dumps(reply, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
