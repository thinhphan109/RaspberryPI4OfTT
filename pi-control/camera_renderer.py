"""MP4 renderer library and independent per-job systemd worker."""
import argparse


def render_session(session):
    import camera_agent as c
    note,ok=session['note'],False
    try:
        c.check_target(session['target']);folder=c.Path(session['folder'])
        if session['frames']<2:raise ValueError('Chưa đủ 2 ảnh để ghép; ảnh đã chụp vẫn được giữ')
        if session['target']['trial'] and session['bytes']>64*1024**2:raise ValueError('Vượt giới hạn RAM')
        command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-n','-framerate','30','-i',str(folder/'frame-%06d.jpg'),'-an',
                 '-c:v','libx264','-threads','1','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'timelapse.mp4')]
        if session['target']['trial']:command[-1:-1]=['-fs',str(min(32*1024**2,max(0,128*1024**2-c.trial_usage())))]
        process=c.subprocess.Popen(command,stdout=c.subprocess.DEVNULL,stderr=c.subprocess.DEVNULL)
        deadline=c.time.monotonic()+1800
        while process.poll() is None:
            c.time.sleep(.5)
            try:
                c.check_target(session['target'])
                if c.time.monotonic()>deadline:raise ValueError('Ghép video quá thời hạn; ảnh gốc vẫn được giữ')
            except Exception:
                process.terminate()
                try:process.wait(timeout=3)
                except c.subprocess.TimeoutExpired:process.kill();process.wait()
                raise
        if process.returncode:raise ValueError('Ghép video thất bại; ảnh gốc vẫn được giữ')
        probe=c.subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','json',str(folder/'timelapse.mp4')],capture_output=True,text=True,timeout=10,check=True)
        streams=c.json.loads(probe.stdout).get('streams',[])
        if not streams or int(streams[0].get('nb_frames',0))!=session['frames']:raise ValueError('Video chưa đủ số ảnh; giữ ảnh gốc để ghép lại trên SSD')
        ok=True
    except Exception as error:note=str(error)[:200]
    record=dict(id=session['id'],mode=session['mode'],frames=session['frames'],bytes=session['bytes'],started=session['started'],
                duration=session.get('duration',0),state='ready' if ok else 'incomplete',note=note)
    try:
        c.check_target(session['target']);c.atomic_json(c.Path(session['folder'])/'session.json',record)
    except (OSError,ValueError):pass
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job-id',required=True);args=parser.parse_args()
    from render_jobs import validated_session,write_private,job_path
    session=validated_session(args.job_id)
    result=render_session(session)
    write_private(job_path(args.job_id,True),result)
    if result['state']!='ready':raise SystemExit(1)


if __name__=='__main__':main()
