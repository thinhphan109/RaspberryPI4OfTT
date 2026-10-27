"""Private webcam capture, bounded timelapse and calibrated position selection.

One FFmpeg reader owns V4L2. Frames and preview stay in RAM. Recording is an
explicit action; absent external storage never falls back to the SD filesystem.
"""
import base64
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import socketserver
import subprocess
import threading
import time
import uuid
from PIL import Image, ImageChops, ImageStat
from camera_policy import PositionGate, ViewerPower, number, regions
from runtime_config import modular, location, CONFIG as RUNTIME_CONFIG

RUNTIME = Path(f'/run/user/{os.getuid()}')
STATE = Path(os.environ.get('PI_CAMERA_STATE', str(location('camera_state',Path.home() / '.local/state/pi-camera'))))
TRIAL = Path(os.environ.get('PI_CAMERA_TRIAL', str(RUNTIME / 'pi-camera-trial')))
SOCKET = Path(os.environ.get('PI_CAMERA_SOCKET', str(RUNTIME / 'pi-camera.sock')))
DEVICE = '/dev/v4l/by-id/usb-Generic_Web_Camera_20250708V1.000-video-index0'
MAX_FRAME = 2 * 1024 * 1024
SESSION_ID = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{8}$')
LOCK = threading.RLock()


def camera_device():
    if not modular():return DEVICE
    configured=RUNTIME_CONFIG.get('camera_device','auto')
    if configured!='auto':return configured
    devices=sorted(Path('/dev/v4l/by-id').glob('*-video-index0'))
    if len(devices)!=1:raise ValueError('Chọn đúng một webcam USB trong cấu hình Camera')
    return str(devices[0])


def atomic_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def external_mounts():
    """Only block devices explicitly reported on USB; never arbitrary paths."""
    result = subprocess.run(['lsblk', '-J', '-o', 'NAME,TRAN,FSTYPE,MOUNTPOINTS,UUID'],
                            capture_output=True, text=True, timeout=4, check=True)
    mounts = []

    def walk(items, usb=False):
        for item in items:
            on_usb = usb or item.get('tran') == 'usb'
            if on_usb and item.get('fstype') in ('ext4', 'exfat', 'ntfs', 'ntfs3', 'vfat', 'xfs', 'btrfs'):
                for mount in item.get('mountpoints') or []:
                    if modular():
                        if mount==RUNTIME_CONFIG['data_mount'] and item.get('uuid')==RUNTIME_CONFIG['data_uuid'] and item['fstype']=='ext4':
                            mounts.append(dict(path=mount,uuid=item['uuid'],fs=item['fstype']))
                        continue
                    if mount and (mount.startswith('/media/') or mount.startswith('/mnt/')):
                        mounts.append(dict(path=mount, uuid=item.get('uuid') or '', fs=item['fstype']))
            walk(item.get('children') or [], on_usb)
    walk(json.loads(result.stdout)['blockdevices'])
    return mounts


def storage_target(choice, mounts=None):
    if choice == 'ram':
        TRIAL.mkdir(mode=0o700, parents=True, exist_ok=True)
        if TRIAL.is_symlink() or TRIAL.stat().st_dev != RUNTIME.stat().st_dev:
            raise ValueError('Vùng thử RAM không hợp lệ')
        return dict(root=str(TRIAL), mount='', device=TRIAL.stat().st_dev, trial=True)
    candidates = external_mounts() if mounts is None else mounts
    found = next((m for m in candidates if m['path'] == choice), None)
    if not found:
        raise ValueError('SSD chưa được gắn/mount; không chuyển sang ghi thẻ SD')
    mount = Path(choice)
    if mount.is_symlink() or not mount.is_mount() or mount.stat().st_dev == Path('/').stat().st_dev:
        raise ValueError('Đích lưu không phải ổ ngoài đang mount')
    root = mount / 'PiCamera'
    if root.is_symlink():
        raise ValueError('Đích lưu không được là liên kết')
    descriptor = os.open(mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_dev != mount.stat().st_dev:
            raise ValueError('Ổ lưu đã thay đổi')
        try: os.mkdir('PiCamera',mode=0o700,dir_fd=descriptor)
        except FileExistsError: pass
    finally:
        os.close(descriptor)
    return dict(root=str(root), mount=choice, device=root.stat().st_dev, uuid=found['uuid'], trial=False)


def check_target(target):
    root = Path(target['root'])
    if root.is_symlink() or not root.is_dir() or root.stat().st_dev != target['device']:
        raise ValueError('Ổ lưu đã mất kết nối; đã dừng ghi')
    if target['mount']:
        mount = Path(target['mount'])
        if not mount.is_mount() or mount.stat().st_dev != target['device']:
            raise ValueError('SSD không còn được mount; đã dừng ghi')
    free = os.statvfs(root)
    reserve = 32 * 1024**2 if target['trial'] else 1024**3
    if free.f_bavail * free.f_frsize < reserve:
        raise ValueError('Ổ lưu sắp đầy; đã dừng ghi')


@contextmanager
def photo_session(ident, storage):
    """Open an existing session without creating directories or following links."""
    if not isinstance(ident, str) or not SESSION_ID.fullmatch(ident):
        raise ValueError('Mã phiên không hợp lệ')
    descriptors = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if storage == 'ram':
            root = os.open(TRIAL, flags)
            descriptors.append(root)
            if os.fstat(root).st_dev != RUNTIME.stat().st_dev:
                raise ValueError('Vùng thử RAM không hợp lệ')
        else:
            if not isinstance(storage, str) or not any(m['path'] == storage for m in external_mounts()):
                raise ValueError('SSD chưa được kết nối hoặc mount')
            mount = Path(storage)
            if not mount.is_mount() or mount.is_symlink():
                raise ValueError('Ổ lưu không còn kết nối')
            device = mount.stat().st_dev
            if device == Path('/').stat().st_dev:
                raise ValueError('Đích lưu không phải SSD')
            base = os.open(mount, flags)
            descriptors.append(base)
            if os.fstat(base).st_dev != device:
                raise ValueError('Ổ lưu đã thay đổi')
            root = os.open('PiCamera', flags, dir_fd=base)
            descriptors.append(root)
            if os.fstat(root).st_dev != device:
                raise ValueError('Ổ lưu đã thay đổi')
        directory = os.open(ident, flags, dir_fd=root)
        descriptors.append(directory)
        if os.fstat(directory).st_dev != os.fstat(root).st_dev:
            raise ValueError('Thư mục phiên không hợp lệ')
        manifest = os.open('session.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(manifest, 'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError('Thông tin phiên không hợp lệ')
            data = handle.read(65537)
        info = json.loads(data) if len(data) <= 65536 else None
        if not isinstance(info, dict) or info.get('id') != ident:
            raise ValueError('Thông tin phiên không hợp lệ')
        yield directory
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def fingerprints(jpeg, rois):
    with Image.open(io.BytesIO(jpeg)) as image:
        image.load()
        width, height = image.size
        result = []
        for x, y, w, h in regions(rois):
            crop = image.crop((round(x * width), round(y * height), round((x+w)*width), round((y+h)*height)))
            result.append(crop.convert('L').resize((32, 24)))
        return result


def valid_recording_jpeg(jpeg):
    """Strict decode at the recording boundary; never enable truncated-image loading."""
    with Image.open(io.BytesIO(jpeg)) as image:
        if image.format != 'JPEG' or image.width > 1280 or image.height > 720:
            raise OSError('Khung ảnh webcam không hợp lệ')
        image.load()


def difference(left, right):
    return ImageStat.Stat(ImageChops.difference(left, right)).mean[0] / 255


def trial_usage():
    return sum(p.stat().st_size for p in TRIAL.glob('*/*') if p.is_file() and not p.is_symlink())


class Camera:
    def __init__(self):
        self.process = None
        self.closing = False
        self.frame = None
        self.frame_at = 0
        self.sequence = 0
        self.error = ''
        self.session = None
        self.rendering = False
        self.render_session = None
        self.worker = None
        self.config = {}
        self.references = None
        self.scores = None
        self.last_poll = 0
        self.mounts = []
        self.mounts_at = 0
        self.targets = {'ram': None}
        self.last_result = None
        self.frozen = None
        self.frozen_at = 0
        self.opened_at = 0
        self.power_policy = ViewerPower()
        self.auto_retry_at = 0
        self.dropped_frames = 0
        self.storage_uuid = RUNTIME_CONFIG['data_uuid'] if modular() else ''
        try:
            saved_storage = json.loads((STATE/'storage.json').read_text())
            value = saved_storage.get('uuid', '')
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9-]{1,80}', value):
                self.storage_uuid = value
        except (OSError, ValueError, AttributeError):
            pass
        try:
            saved=json.loads((STATE/'power.json').read_text())
            if type(saved.get('automatic')) is bool:
                self.power_policy.automatic=saved['automatic']
        except (OSError,ValueError,AttributeError):
            pass
        try:
            config = json.loads((STATE/'calibration.json').read_text())
            self.references = fingerprints((STATE/'reference.jpg').read_bytes(), config['regions'])
            self.config = config
        except (OSError, ValueError, KeyError):
            pass
        if modular():
            try:
                from render_jobs import pending
                running=pending()
                if running:
                    self.rendering=True;self.render_session=running
                    threading.Thread(target=self.recover_render,args=(running,),daemon=True).start()
            except Exception:self.error='Chưa đọc được job ghép trước; kiểm tra worker Render'

    def recover_render(self,session):
        from render_jobs import wait
        try:record=wait(session['id'])
        except Exception as error:
            record=dict(id=session['id'],mode=session['mode'],frames=session['frames'],bytes=session['bytes'],started=session['started'],
                        duration=session.get('duration',0),state='incomplete',note=str(error)[:200])
        with LOCK:
            self.last_result=dict(record,storage=session['target']['mount'] or 'ram');self.rendering=False;self.render_session=None

    def status(self):
        now = time.monotonic()
        if now - self.mounts_at > 15:
            try:
                self.mounts = external_mounts()
            except (OSError, ValueError, subprocess.SubprocessError):
                self.mounts = []
            self.mounts_at = now
        session = self.session
        return dict(enabled=bool(self.process and self.process.poll() is None),
                    available=bool(self.frame and now-self.frame_at < 3),
                    frame_sequence=self.sequence, error=self.error, resolution='1280 × 720',
                    calibrated=bool(self.references), regions=self.config.get('regions', []),
                    scores=[round(s*100, 1) for s in self.scores] if self.scores else None,
                    threshold=round(self.config.get('threshold', .06)*100, 1), settle=self.config.get('settle',.2),
                    recording=bool(session), rendering=self.rendering, dropped_frames=self.dropped_frames,
                    automatic=self.power_policy.automatic, viewers=len(self.power_policy.viewers),
                    manual_paused=self.power_policy.paused, idle_grace=ViewerPower.GRACE,
                    session=self.session_summary(session),
                    render_session=self.session_summary(self.render_session),
                    tracking=session['gate'].diagnostics(now) if session and session['mode']=='position' else None,
                    calibration_warning=('Vùng mẫu quá rộng; chọn chi tiết nhỏ trên đầu in và mép bàn, tránh vật thể và nền.'
                                         if any(r[2]*r[3]>.35 for r in self.config.get('regions', [])) else ''),
                    last_result=self.last_result, mounts=self.mounts,
                    storage_default=self.default_storage(), storage_uuid=self.storage_uuid,
                    trial_note='RAM: tối đa 10 phút / 64 MiB mỗi phiên; tổng 128 MiB. Mất khi reboot.')

    @staticmethod
    def session_summary(session):
        if not session:
            return None
        summary = {k:v for k,v in session.items() if k in ('id','mode','frames','bytes','started','duration','note')}
        summary['storage'] = session['target']['mount'] or 'ram'
        return summary

    def default_storage(self):
        if not self.storage_uuid:
            return 'ram'
        return next((m['path'] for m in self.mounts if m['uuid'] == self.storage_uuid), None)

    def set_storage(self, choice):
        if self.session or self.rendering:
            raise ValueError('Kết thúc ghi/ghép trước khi đổi nơi lưu')
        if not isinstance(choice, str):
            raise ValueError('Đích lưu không hợp lệ')
        target = storage_target(choice)
        check_target(target)
        value = '' if target['trial'] else target['uuid']
        if not target['trial'] and not re.fullmatch(r'[A-Za-z0-9-]{1,80}', value):
            raise ValueError('Ổ ngoài không có UUID hợp lệ')
        if value != self.storage_uuid:
            atomic_json(STATE/'storage.json', dict(uuid=value))
            self.storage_uuid = value
        self.mounts_at = 0

    def enable(self):
        if self.process and self.process.poll() is None:
            return
        if self.worker and self.worker.is_alive():
            raise ValueError('Camera đang đóng; thử lại sau vài giây')
        device=camera_device()
        if not Path(device).exists():
            raise ValueError('Không thấy webcam USB đã cấu hình')
        # MJPEG is already encoded by the webcam: no decode/re-encode for preview.
        command = ['ffmpeg','-hide_banner','-loglevel','error','-nostdin',
                   '-f','v4l2','-input_format','mjpeg','-video_size','1280x720','-framerate','30',
                   '-i',device,'-an','-c:v','copy','-f','mjpeg','pipe:1']
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.closing = False
        self.opened_at = time.monotonic()
        self.error = ''
        process = self.process
        self.worker = threading.Thread(target=self.capture, args=(process,), daemon=True)
        self.worker.start()

    def disable(self):
        if self.session:
            self.stop('Camera đã tắt')
        if self.process:
            self.closing = True
            self.process.terminate()
        self.frame = None
        self.frame_at = 0

    def power_tick(self):
        now=time.monotonic()
        decision=self.power_policy.decision(bool(self.session),now)
        running=bool(self.process and self.process.poll() is None)
        if decision is True and not running and now>=self.auto_retry_at:
            try:
                self.enable()
                self.auto_retry_at=now+5
            except (ValueError,OSError) as exc:
                self.error=str(exc)[:200]
                self.auto_retry_at=now+5
        elif decision is False and running:
            self.disable()

    def check_stream(self):
        # disable() clears frame_at while SIGTERM is still in flight. That is
        # an intentional close, not evidence of a stalled USB camera.
        if (self.process and not self.closing and self.process.poll() is None
                and time.monotonic()-max(self.opened_at,self.frame_at)>8):
            self.error = 'Webcam không gửi ảnh trong 8 giây; đã dừng camera'
            if self.session:
                self.stop(self.error)
            self.closing = True
            self.process.terminate()

    def set_automatic(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Chế độ tự động không hợp lệ')
        atomic_json(STATE/'power.json',dict(automatic=enabled))
        self.power_policy.automatic=enabled
        self.power_policy.paused=False
        self.power_policy.idle_since=None
        self.auto_retry_at=0
        self.power_tick()

    def capture(self, process):
        buffer = b''
        last = 0
        try:
            while process.poll() is None:
                data = process.stdout.read(65536)
                if not data:
                    break
                buffer += data
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', max(start, 0)+2)
                    if start < 0 or end < 0:
                        break
                    jpeg, buffer = buffer[start:end+2], buffer[end+2:]
                    now = time.monotonic()
                    if len(jpeg) > MAX_FRAME or now-last < .09:
                        continue
                    last = now
                    with LOCK:
                        self.frame, self.frame_at = jpeg, now
                        self.sequence += 1
                        self.tick(jpeg, now)
                if len(buffer) > MAX_FRAME:
                    raise ValueError('Khung ảnh webcam quá lớn')
        except Exception as exc:
            with LOCK:
                self.error = str(exc)[:200]
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.stdout.close()
            with LOCK:
                if self.session:
                    self.stop('Webcam ngắt kết nối')
                self.frame = None
                if self.process is process:
                    self.process = None
                    self.closing = False
                    self.auto_retry_at=time.monotonic()+5

    def calibrate(self, payload):
        if self.session or self.rendering:
            raise ValueError('Kết thúc phiên trước khi đổi vùng ảnh')
        if not self.frozen or time.monotonic()-self.frozen_at > 300:
            raise ValueError('Bấm Giữ ảnh mẫu trước; ảnh mẫu có hiệu lực 5 phút')
        jpeg = self.frozen
        rois = regions(payload.get('regions'))
        threshold = number(payload.get('threshold', 6), 2, 20, 'Sai lệch cho phép')/100
        settle = number(payload.get('settle', .2), .1, 2, 'Thời gian ổn định')
        try:
            refs = fingerprints(jpeg, rois)
        except OSError:
            raise ValueError('Ảnh mẫu bị lỗi. Bấm Giữ ảnh mẫu để lấy ảnh mới.') from None
        if any(ImageStat.Stat(ref).stddev[0] < 6 for ref in refs):
            raise ValueError('Vùng ảnh quá phẳng; chọn chi tiết dễ nhận ra trên đầu in và bàn in')
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        reference = STATE/'reference.jpg'
        with open(reference.with_suffix('.tmp'), 'wb') as handle:
            handle.write(jpeg)
        os.chmod(reference.with_suffix('.tmp'), 0o600)
        os.replace(reference.with_suffix('.tmp'), reference)
        config = dict(regions=rois, threshold=threshold,settle=settle)
        atomic_json(STATE/'calibration.json', config)
        self.references, self.config = refs, config

    def fresh_frame(self):
        if not self.frame or time.monotonic()-self.frame_at > 3:
            raise ValueError('Chưa có ảnh mới từ webcam')
        return self.frame

    def start(self, payload):
        if self.session or self.rendering:
            raise ValueError('Một phiên đang ghi hoặc đang ghép video')
        self.fresh_frame()
        mode = payload.get('mode')
        if mode not in ('interval','position'):
            raise ValueError('Chế độ không hợp lệ')
        if mode == 'position' and not self.references:
            raise ValueError('Cần lưu hai vùng vị trí chụp trước')
        interval = number(payload.get('interval', 5), 2, 60, 'Chu kỳ chụp')
        # Refresh UUID resolution at the write boundary, never use a stale mount path.
        self.mounts = external_mounts()
        self.mounts_at = time.monotonic()
        choice = payload.get('storage', self.default_storage())
        if choice is None:
            raise ValueError('SSD đã lưu chưa kết nối; gắn lại ổ hoặc chủ động chọn RAM để thử')
        if not isinstance(choice, str):
            raise ValueError('Đích lưu không hợp lệ')
        target = storage_target(choice)
        check_target(target)
        if target['trial'] and trial_usage() > 64*1024**2:
            raise ValueError('Vùng thử RAM đã dùng hơn 64 MiB; tải rồi xóa phiên cũ trước')
        ident = time.strftime('%Y%m%dT%H%M%S', time.gmtime())+'-'+uuid.uuid4().hex[:8]
        folder = Path(target['root'])/ident
        folder.mkdir(mode=0o700)
        session = dict(id=ident, mode=mode, frames=0, bytes=0, started=int(time.time()),
                       duration=0, note='Chờ rời rồi trở lại vị trí mẫu' if mode=='position' else 'Đang chụp theo thời gian',
                       target=target, folder=str(folder), interval=interval, next_at=0,
                       monotonic=time.monotonic(), gate=PositionGate(threshold=self.config.get('threshold', .06),settle=self.config.get('settle',.2)))
        atomic_json(folder/'session.json', dict(id=ident,mode=mode,started=session['started'],state='recording'))
        self.targets[choice] = target
        self.session = session
        self.error = ''

    def tick(self, jpeg, now):
        session = self.session
        if not session:
            return
        try:
            session['duration'] = round(now-session['monotonic'])
            if session['duration'] >= (600 if session['target']['trial'] else 86400):
                self.stop('Đã đạt giới hạn thời gian')
                return
            if session['mode'] == 'position':
                try:
                    current = fingerprints(jpeg, self.config['regions'])
                except OSError:
                    self.dropped_frames += 1
                    self.scores = None
                    session['gate'].feed([float('nan'), float('nan')], now)
                    session['note'] = 'Đã bỏ qua khung ảnh lỗi; tiếp tục chờ vị trí chụp'
                    return
                self.scores = [difference(a,b) for a,b in zip(current, self.references)]
                shoot = session['gate'].feed(self.scores, now)
                session['note'] = {
                    'waiting_departure':'Chờ rời vị trí mẫu; chưa đủ điều kiện chụp',
                    'leaving':'Đang xác nhận rời vị trí mẫu',
                    'waiting_return':'Đã rời mẫu; chờ đầu in và bàn in trở lại',
                    'settling':'Đã về vị trí; chờ ổn định',
                    'cooldown':'Đã về vị trí; chờ hết khoảng cách giữa hai ảnh',
                    'captured':'Đã chụp; chờ chu kỳ rời và trở lại tiếp theo',
                }.get(session['gate'].phase, 'Đang kiểm tra vị trí')
            else:
                shoot = now >= session['next_at']
            if not shoot:
                return
            if session['mode'] == 'interval':
                try:
                    valid_recording_jpeg(jpeg)
                except OSError:
                    self.dropped_frames += 1
                    session['note'] = 'Đã bỏ qua khung ảnh lỗi; chờ ảnh tiếp theo'
                    return
                session['note'] = 'Đang chụp theo thời gian'
            check_target(session['target'])
            limit = 64*1024**2 if session['target']['trial'] else 5*1024**3
            if session['bytes']+len(jpeg) > limit or session['frames'] >= 20000:
                self.stop('Đã đạt giới hạn dung lượng / số ảnh')
                return
            if session['target']['trial'] and trial_usage()+len(jpeg) > 96*1024**2:
                self.stop('Vùng thử RAM đã đạt giới hạn; dành chỗ ghép video')
                return
            path = Path(session['folder'])/f"frame-{session['frames']:06d}.jpg"
            directory = os.open(session['folder'],os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if os.fstat(directory).st_dev != session['target']['device']:
                    raise ValueError('Ổ lưu đã thay đổi; đã dừng ghi')
                descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(jpeg)
            finally:
                os.close(directory)
            session['frames'] += 1
            session['bytes'] += len(jpeg)
            session['next_at'] = now+session['interval']
        except Exception as exc:
            self.error = str(exc)[:200]
            self.stop(self.error)

    def stop(self, note='Đã kết thúc phiên'):
        session, self.session = self.session, None
        if not session:
            return
        session['note'] = note
        self.rendering = True
        self.render_session = session
        threading.Thread(target=self.render, args=(session,), daemon=True).start()

    def render(self, session):
        try:
            if modular():
                from render_jobs import submit, wait
                record=wait(submit(session))
            else:
                from camera_renderer import render_session
                record=render_session(session)
        except Exception as error:
            record=dict(id=session['id'],mode=session['mode'],frames=session['frames'],bytes=session['bytes'],
                        started=session['started'],duration=session.get('duration',0),state='incomplete',note=str(error)[:200])
        with LOCK:
            self.last_result=dict(record,storage=session['target']['mount'] or 'ram')
            self.rendering=False
            self.render_session=None

    def recordings(self):
        # Discover only this application's folders on currently mounted USB media.
        targets = [storage_target('ram')]
        for mount in self.mounts:
            root = Path(mount['path'])/'PiCamera'
            if root.is_dir() and not root.is_symlink():
                targets.append(dict(root=str(root), mount=mount['path'],device=root.stat().st_dev,trial=False))
        result = []
        for target in targets:
            for folder in sorted(Path(target['root']).iterdir(), reverse=True)[:200]:
                if not SESSION_ID.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir():
                    continue
                try:
                    info = json.loads((folder/'session.json').read_text())
                    if not isinstance(info, dict):
                        continue
                    # The start manifest deliberately has no periodic counter writes.
                    # Overlay only the job belonging to this exact mounted folder.
                    job = next((s for s in (self.session, self.render_session)
                                if s and s['id']==folder.name and Path(s['folder'])==folder), None)
                    if job:
                        info.update(self.session_summary(job))
                        info['state'] = 'recording' if job is self.session else 'rendering'
                    elif info.get('state') == 'recording':
                        info.update(state='interrupted', frames=None,
                                    note='Phiên đã bị gián đoạn; ảnh gốc vẫn được giữ')
                    info.update(id=folder.name, storage=target['mount'] or 'ram',
                                video=(folder/'timelapse.mp4').is_file() and info.get('state')=='ready')
                    result.append(info)
                except (OSError, ValueError):
                    continue
        return result[:100]

    def recording_path(self, ident, storage):
        if not isinstance(ident, str) or not SESSION_ID.fullmatch(ident):
            raise ValueError('Mã phiên không hợp lệ')
        records = self.recordings()
        if not any(r['id']==ident and r['storage']==storage for r in records):
            raise ValueError('Không thấy phiên trên ổ lưu đang kết nối')
        if storage == 'ram':
            root = TRIAL
        elif any(m['path']==storage for m in self.mounts):
            root = Path(storage)/'PiCamera'
        else:
            raise ValueError('Ổ lưu không còn kết nối')
        folder = root/ident
        if folder.is_symlink() or folder.resolve().parent != root.resolve():
            raise ValueError('Đường dẫn không hợp lệ')
        return folder

    def dispatch(self, payload):
        action = payload.get('action')
        if action == 'photos':
            with photo_session(payload.get('id'), payload.get('storage')) as directory:
                indices = []
                with os.scandir(directory) as entries:
                    for count, entry in enumerate(entries):
                        if count >= 50000:
                            raise ValueError('Thư mục phiên có quá nhiều tệp')
                        match = re.fullmatch(r'frame-(\d{6})\.jpg', entry.name)
                        if match and int(match[1]) < 20000 and entry.is_file(follow_symlinks=False):
                            indices.append(int(match[1]))
                return dict(indices=sorted(indices), total=len(indices))
        if action == 'photo':
            index = payload.get('index')
            if type(index) is not int or not 0 <= index < 20000:
                raise ValueError('Số ảnh không hợp lệ')
            with photo_session(payload.get('id'), payload.get('storage')) as directory:
                descriptor = os.open(f'frame-{index:06d}.jpg', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(descriptor, 'rb') as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ValueError('Ảnh không hợp lệ')
                    jpeg = handle.read(MAX_FRAME + 1)
                if len(jpeg) > MAX_FRAME or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                    raise ValueError('Ảnh JPEG không hợp lệ')
                return dict(jpeg=base64.b64encode(jpeg).decode())
        if action == 'status':
            return self.status()
        if action == 'frame':
            return dict(jpeg=base64.b64encode(self.fresh_frame()).decode())
        if action == 'freeze':
            self.frozen, self.frozen_at = self.fresh_frame(), time.monotonic()
            return dict(jpeg=base64.b64encode(self.frozen).decode())
        if action == 'power':
            if type(payload.get('enabled')) is not bool:
                raise ValueError('Trạng thái camera không hợp lệ')
            if not payload['enabled'] and self.session:
                raise ValueError('Đang ghi timelapse; kết thúc và ghép phiên trước khi tắt camera')
            if payload['enabled']:
                self.enable()
            else:
                self.disable()
            self.power_policy.manual(payload['enabled'])
        elif action == 'automatic':
            self.set_automatic(payload.get('enabled'))
        elif action == 'storage':
            self.set_storage(payload.get('storage'))
        elif action == 'watch':
            self.power_policy.watch(payload.get('viewer'),payload.get('watching'),time.monotonic())
            self.power_tick()
        elif action == 'calibrate':
            self.calibrate(payload)
        elif action == 'start':
            self.start(payload)
        elif action == 'stop':
            self.stop()
        elif action == 'list':
            self.status()
            return self.recordings()
        elif action == 'download':
            folder = self.recording_path(payload.get('id'),payload.get('storage'))
            path = folder/'timelapse.mp4'
            if path.is_symlink() or not path.is_file() or not any(
                    r['id']==folder.name and r['storage']==payload.get('storage') and r['video'] for r in self.recordings()):
                raise ValueError('Video chưa sẵn sàng')
            return dict(path=str(path))
        elif action == 'render':
            if self.session or self.rendering:
                raise ValueError('Một phiên đang ghi hoặc đang ghép')
            folder = self.recording_path(payload.get('id'),payload.get('storage'))
            record = next(r for r in self.recordings() if r['id']==folder.name and r['storage']==payload.get('storage'))
            if record['state']=='ready':
                raise ValueError('Video đã ghép xong')
            frames = sorted(folder.glob('frame-??????.jpg'))
            if not 2 <= len(frames) <= 20000 or any(p.is_symlink() or p.name!=f'frame-{i:06d}.jpg' for i,p in enumerate(frames)):
                raise ValueError('Cần chuỗi ảnh gốc liên tục, ít nhất 2 ảnh')
            target = dict(root=str(folder.parent),mount='' if payload.get('storage')=='ram' else payload['storage'],
                          device=folder.stat().st_dev,trial=payload.get('storage')=='ram')
            check_target(target)
            output = folder/'timelapse.mp4'
            if output.is_symlink():
                raise ValueError('Video không được là liên kết')
            output.unlink(missing_ok=True)
            session = dict(id=folder.name,mode=record['mode'],frames=len(frames),bytes=sum(p.stat().st_size for p in frames),
                           started=record['started'],folder=str(folder),target=target,note='Ghép từ ảnh gốc')
            self.rendering = True
            self.render_session = session
            threading.Thread(target=self.render,args=(session,),daemon=True).start()
        elif action == 'delete':
            folder = self.recording_path(payload.get('id'),payload.get('storage'))
            if self.rendering or self.session:
                raise ValueError('Kết thúc ghi/ghép video trước khi xóa')
            # Only fixed app-generated names, never recursive deletion of supplied paths.
            files = list(folder.iterdir())
            if any(p.is_symlink() or not p.is_file() or not re.fullmatch(
                    r'(?:frame-\d{6}\.jpg|timelapse\.mp4|session\.(?:json|tmp))',p.name) for p in files):
                raise ValueError('Thư mục có dữ liệu khác; không tự xóa')
            for path in files:
                path.unlink()
            folder.rmdir()
        else:
            raise ValueError('Thao tác camera không hợp lệ')
        return self.status()


CAMERA = None


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            raw = self.rfile.readline(65537)
            if len(raw) > 65536 or not raw.endswith(b'\n'):
                raise ValueError('Yêu cầu quá lớn')
            payload = json.loads(raw)
            if not isinstance(payload,dict):
                raise ValueError('Yêu cầu không hợp lệ')
            with LOCK:
                result = dict(ok=True,data=CAMERA.dispatch(payload))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            result = dict(ok=False,error=str(exc)[:200])
        self.wfile.write(json.dumps(result,ensure_ascii=False).encode()+b'\n')


def main():
    global CAMERA
    os.umask(0o077)
    CAMERA = Camera()
    if SOCKET.exists():
        SOCKET.unlink()
    server = socketserver.ThreadingUnixStreamServer(str(SOCKET),Handler)
    server.daemon_threads = True
    os.chmod(SOCKET,0o600)

    def shutdown(*_):
        with LOCK:
            if CAMERA.process:
                CAMERA.process.terminate()
        # A recording interrupted by service shutdown remains recoverable as JPEGs.
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    def watchdog():
        while True:
            time.sleep(1)
            with LOCK:
                CAMERA.power_tick()
                CAMERA.check_stream()
    threading.Thread(target=watchdog,daemon=True).start()
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
