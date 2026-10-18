"""Pi-only smoke test. Temporarily changes playback; restores original video/state."""
import json
from pathlib import Path
import socket
import subprocess
import time
import media_agent as browser

def call(payload):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15);sock.connect('/run/user/1000/pi-media.sock')
        sock.sendall(json.dumps(payload).encode()+b'\n')
        response=json.loads(sock.makefile('rb').readline())
    if not response['ok']:raise RuntimeError(response.get('error'))
    return response['data']

def wait_video(url,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        s=call(dict(action='status'))
        if s.get('url')==url and s.get('has_video') and not s.get('ad'):
            ready=browser.evaluate('(()=>{const v=document.querySelector("video");return {id:document.querySelector("#movie_player")?.getVideoData?.().video_id,ready:v?.readyState}})()')
            if ready.get('id')==url.split('v=')[1] and ready.get('ready',0)>=3:return s
        time.sleep(1)
    raise RuntimeError('Video did not become ready')

before=call(dict(action='status'))
assert before.get('has_video') and not before.get('ad') and before.get('url')
assert not before['preferences']['sleep']['active'] and not before['preferences']['sleep']['expired'],'Do not disturb user timer'
assert before.get('up_next'),'Need eligible next recommendation'
assert before['nonstop'],'Test requires existing Nonstop enabled'
ident=before['url'].split('v=')[1]
changed=False
try:
    changed=True
    skipped=call(dict(action='dislike'))
    assert any(x['id']==ident for x in skipped['preferences']['disliked'])
    expected=before['up_next']['url']
    current=wait_video(expected)
    assert not current.get('up_next') or current['up_next']['url']!=before['url']
    call(dict(action='undislike',id=ident))
    call(dict(action='play',url=before['url']));wait_video(before['url'])
    browser.evaluate(f'(()=>{{const v=document.querySelector("video");v.currentTime={before["position"]};return true}})()')
    current=call(dict(action='status'))
    assert not current.get('up_next') or current['up_next']['url']!=expected,'Recently played recommendation reselected'
    print('PASS live dislike/skip/undo and recent-video exclusion',flush=True)
    call(dict(action='sleep',minutes=1))
    config=Path.home()/'.local/state/pi-media/nonstop.json';stamp=config.stat().st_mtime_ns
    fade_deadline=time.monotonic()+25
    while time.monotonic()<fade_deadline:
        faded=call(dict(action='status'))
        if faded['volume']<before['volume']:break
        time.sleep(2)
    assert faded['preferences']['sleep']['active']
    assert faded['volume']<before['volume'],'Sleep did not lower video volume'
    print('PASS live fade started; waiting for actual one-minute expiry',flush=True)
    deadline=time.monotonic()+65
    while time.monotonic()<deadline:
        current=call(dict(action='status'))
        if current['preferences']['sleep']['expired'] and current['paused']:break
        time.sleep(2)
    assert current['preferences']['sleep']['expired'] and current['paused'] and current['volume']==0
    time.sleep(7)
    current=call(dict(action='status'))
    assert current['paused'] and current['nonstop'] and not current['autoplay']
    assert config.stat().st_mtime_ns==stamp,'Periodic fade/expiry wrote settings'
    subprocess.run(['systemctl','--user','restart','pi-media'],check=True)
    time.sleep(4)
    current=call(dict(action='status'))
    assert current['paused'] and current['preferences']['sleep']['expired'] and current['nonstop']
    print('PASS actual expiry, Nonstop priority, restart latch and no periodic settings write',flush=True)
finally:
    if changed:
        current=call(dict(action='status'))
        if any(x['id']==ident for x in current['preferences']['disliked']):call(dict(action='undislike',id=ident))
        if current['preferences']['sleep']['active']:call(dict(action='sleep_cancel'))
        call(dict(action='play',url=before['url']))
        wait_video(before['url'])
        call(dict(action='volume',value=before['volume']))
        browser.evaluate(f'(()=>{{const v=document.querySelector("video");v.currentTime={before["position"]};v.muted={json.dumps(before["muted"])};'+('v.pause();' if before['paused'] else 'v.play().catch(()=>{});')+'return true})()')
        restored=call(dict(action='status'))
        if before['paused'] and not restored['manual_pause']:call(dict(action='toggle'));call(dict(action='toggle'))
        print(json.dumps(dict(restored_url=restored['url'],restored_volume=restored['volume'],nonstop=restored['nonstop'],timer=restored['preferences']['sleep'])),flush=True)
