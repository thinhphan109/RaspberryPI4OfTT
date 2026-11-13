"""Render the mini display in RAM and prepare uploaded clips for playback."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import time
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

import mini_display_store as store


SIZE = (320, 240)
OBSERVER = Path('/run/pi-control-observer/metrics.json')
ASSETS = Path(__file__).resolve().parent / 'static'
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
SANS = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
VIETNAM = ZoneInfo('Asia/Ho_Chi_Minh')
FALLBACK = 'Pi-Fallback'
RECOVERY_SECONDS = 8


@lru_cache(maxsize=24)
def typeface(face, size):
    return ImageFont.truetype(face, size)


def local_network():
    try:
        links = json.loads(subprocess.check_output(
            ['/usr/sbin/ip', '-j', '-4', 'address', 'show', 'up', 'scope', 'global'], timeout=2))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    links.sort(key=lambda link: link['ifname'] != 'wlan0')
    for link in links:
        addresses = link.get('addr_info', [])
        if not addresses:
            continue
        interface = link['ifname']
        try:
            profile = nmcli('GENERAL.CONNECTION', 'device', 'show', interface)
        except (OSError, subprocess.SubprocessError):
            return None
        hotspot = profile == FALLBACK
        name = profile if profile not in ('', '--') else interface
        if hotspot:
            try:
                name = nmcli('802-11-wireless.ssid', 'connection', 'show', 'id', FALLBACK) or name
            except (OSError, subprocess.SubprocessError):
                pass
        return {'ip': addresses[0]['local'], 'name': name, 'interface': interface, 'hotspot': hotspot}
    return {}


def nmcli(field, *args):
    return subprocess.check_output(
        ['/usr/bin/nmcli', '--escape', 'no', '-g', field, *args],
        text=True, timeout=2, stderr=subprocess.DEVNULL).strip()


class DisplayEvents:
    def __init__(self):
        self.disconnected = False
        self.recovered_until = 0
        self.hot = False

    def scene(self, metrics, network, now, monotonic):
        fresh = now - metrics.get('timestamp', 0) <= 45
        temperature = metrics.get('temperature')
        power = metrics.get('power') or {}
        self.hot = (fresh and isinstance(temperature, (int, float))
                    and temperature >= (77 if self.hot else 80))
        if network is not None:
            disconnected = not network or network['hotspot']
            if disconnected:
                self.recovered_until = 0
            elif self.disconnected:
                self.recovered_until = monotonic + RECOVERY_SECONDS
            self.disconnected = disconnected
        if network and network['hotspot']:
            return 'hotspot'
        if fresh and power.get('undervoltage'):
            return 'power'
        if self.hot:
            return 'hot'
        if network == {}:
            return 'offline'
        if network and monotonic < self.recovered_until:
            return 'recovered'
        return 'summary'


@lru_cache(maxsize=8)
def mascot(name, size):
    with Image.open(ASSETS / 'mini-cat' / (name + '.png')) as sprite:
        return sprite.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def rescue_qr():
    svg = (ASSETS / 'mini-fallback-qr.svg').read_text(encoding='ascii')
    # Reuse the browser QR's unit squares so the two versions encode the same URL.
    qr = Image.new('RGB', (37, 37), 'white')
    draw = ImageDraw.Draw(qr)
    for x, y in re.findall(r'M(\d+) (\d+)h1v1h-1z', svg):
        draw.point((int(x), int(y)), fill='black')
    return qr.resize((111, 111), Image.Resampling.NEAREST)


def number(value, unit):
    return f'{value:.0f}{unit}' if isinstance(value, (int, float)) else '—'


def rate(value):
    if not isinstance(value, (int, float)):
        return '—'
    return f'{value / 1048576:.1f} MiB/s' if value >= 1048576 else f'{value / 1024:.1f} KiB/s'


def uptime_label(value):
    if not isinstance(value, (int, float)) or value < 0:
        return '—'
    hours, minutes = divmod(int(value) // 60, 60)
    days, hours = divmod(hours, 24)
    return f'{days} ngày {hours} giờ' if days else f'{hours} giờ {minutes} phút'


@lru_cache(maxsize=1)
def background():
    image = Image.new('RGB', SIZE)
    lights = (
        (20, 20, 216, (52, 13, 20)),
        (318, 111, 182, (13, 25, 48)),
        (141, 244, 166, (27, 22, 6)),
    )
    colors = []
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            red, green, blue = 20, 17, 25
            for center_x, center_y, radius, (r, g, b) in lights:
                distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
                glow = max(0, 1 - distance / radius)
                red += round(r * glow)
                green += round(g * glow)
                blue += round(b * glow)
            grid = 3 if x % 24 == 0 or y % 24 == 0 else 0
            colors.append((red + grid, green + grid, blue + grid))
    image.putdata(colors)
    return image


def render(metrics, network, now, scene='summary'):
    network = network or {}
    ip = network.get('ip', 'Chưa có IP')
    ssid = network.get('name', 'Chưa kết nối')
    interface = network.get('interface')
    frame = background().copy()
    draw = ImageDraw.Draw(frame)
    ink, muted, mint = '#f5f7fa', '#b5c4d1', '#a5e1c7'
    amber, line = '#ffcf88', '#35444f'

    def label(value, x, y, size=12, color=muted, face=SANS, width=None):
        font = typeface(face, size)
        if width is not None and draw.textlength(value, font=font) > width:
            while value and draw.textlength(value + '…', font=font) > width:
                value = value[:-1]
            value += '…'
        draw.text((x, y), value, font=font, fill=color, anchor='lt')

    def meter(x, y, value, ceiling, width, color):
        draw.rectangle((x, y, x + width - 1, y + 3), fill='#2a3742')
        if isinstance(value, (int, float)):
            length = round(width * max(0, min(1, value / ceiling)))
            if length:
                draw.rectangle((x, y, x + length - 1, y + 3), fill=color)

    temperature = metrics.get('temperature')
    power = metrics.get('power') or {}
    stale = now.timestamp() - metrics.get('timestamp', 0) > 45
    titles = {'hotspot': 'Cứu hộ mạng', 'offline': 'Cứu hộ mạng', 'recovered': 'Đã kết nối lại',
              'power': 'Nguồn yếu', 'hot': 'Nhiệt độ cao'}
    status = titles.get(scene) or ('Dữ liệu cũ' if stale else 'Đang giảm xung'
                                  if power.get('throttled') else 'Tổng quan')
    tone = mint if status == 'Tổng quan' or scene == 'recovered' else amber
    label(now.strftime('%H:%M'), 16, 13, 14, ink, MONO)
    label(status, 71, 14, 12, tone, width=145)
    label(now.strftime('%d/%m/%Y'), 225, 14, 12, muted, MONO, 79)
    draw.line((16, 35, 303, 35), fill=line)
    if scene in ('hotspot', 'offline', 'recovered'):
        if scene == 'hotspot':
            label('Wi-Fi dự phòng', 16, 51, 13, amber)
            label(ssid, 16, 75, 16, ink, width=170)
            label(ip + ':18765', 16, 101, 13, ink, MONO, 170)
            cat = mascot('hotspot', 85)
            frame.paste(cat, (56, 111), cat)
            if ip == '192.168.50.1':
                frame.paste(rescue_qr(), (192, 56))
            footer = ('Kết nối Wi-Fi rồi quét QR' if ip == '192.168.50.1'
                      else 'Kết nối Wi-Fi rồi mở địa chỉ trên')
        else:
            restored = scene == 'recovered'
            label('Đã có kết nối' if restored else 'Mất kết nối mạng', 16, 76, 20, tone, width=193)
            label(ip, 16, 125, 16, ink, MONO, 189)
            label(ssid, 16, 153, 11, muted, width=189)
            cat = mascot('healthy' if restored else 'offline', 107)
            frame.paste(cat, (211, 50), cat)
            footer = 'Đang trở về trang trước' if restored else 'Đang chờ kết nối mạng'
        draw.line((16, 197, 303, 197), fill=line)
        label(footer, 16, 210, 13, ink, width=288)
        return encode_frame(frame)

    cat = mascot({'power': 'power', 'hot': 'health'}.get(scene, 'network'), 87)
    frame.paste(cat, (220, 39), cat)
    label('Nhiệt độ SoC', 16, 48, 13)
    label(number(temperature, '°C'), 13, 67, 46, amber if scene == 'hot' else ink, MONO, 187)
    meter(16, 116, temperature, 85, 178, amber if scene == 'hot' else mint)
    label(ip, 16, 132, 18, ink, MONO, 183)
    label(ssid, 16, 156, 10, muted, width=181)
    label('Đã chạy ' + uptime_label(metrics.get('uptime')), 16, 177, 11, muted, width=183)
    for y, title, value in (
        (119, 'CPU', metrics.get('cpu')),
        (157, 'RAM', (metrics.get('ram') or {}).get('percent')),
    ):
        label(title, 220, y + 3, 11)
        label(number(value, '%'), 252, y, 16, ink, MONO, 53)
        meter(220, y + 23, value, 100, 83, mint)
    draw.line((16, 197, 303, 197), fill=line)
    disks = {item['mount']: item for item in metrics.get('disks', [])}
    disk = disks.get('/srv/pi-control') or disks.get('/') or {}
    traffic = next((item for item in metrics.get('network', []) if item.get('name') == interface), {})
    free = f'{disk["free"] / 1073741824:.1f} GiB' if 'free' in disk else '—'
    for x, title, value in (
        (16, 'Ổ trống' if '/srv/pi-control' in disks else 'Hệ thống trống', free),
        (120, '↓ Nhận', rate(traffic.get('rx_rate'))),
        (220, '↑ Gửi', rate(traffic.get('tx_rate'))),
    ):
        label(title, x, 204, 11, muted, width=98)
        label(value, x, 219, 12, ink, MONO, 86)
    return encode_frame(frame)


def encode_frame(frame):
    buffer = BytesIO()
    frame.save(buffer, format='PNG')
    return buffer.getvalue()


def convert(pending):
    receipt = store.read_json(store.STORE / 'receipt.json')
    receipt.pop('error', None)
    target = store.STORE / '.encoding.mp4'
    try:
        target.unlink(missing_ok=True)
        command = [
            '/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
            '-protocol_whitelist', 'file', '-threads', '2', '-max_pixels', '4194304',
            '-probesize', '2097152', '-analyzeduration', '3000000',
            '-f', pending['format'], '-i', str(store.STORE / 'source'), '-map', '0:v:0',
            '-an', '-sn', '-dn', '-t', '30', '-filter_threads', '1',
            '-vf', 'fps=10,scale=320:240:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=320:240:(ow-iw)/2:(oh-ih)/2,setsar=1',
            '-threads', '2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target),
        ]
        subprocess.run(command, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        info = json.loads(subprocess.check_output(
            ['/usr/bin/ffprobe', '-v', 'error', '-show_entries', 'stream=nb_frames:format=duration',
             '-of', 'json', str(target)], timeout=5))
        if not 0 < float(info['format']['duration']) <= 30.1 or int(info['streams'][0]['nb_frames']) < 1:
            raise ValueError('Empty or oversized result')
        target.chmod(0o600)
        with store.lock():
            target.replace(store.STORE / 'clip.mp4')
            receipt['clip'] = {'name': pending['name'], 'revision': str(time.time_ns()),
                               'duration': round(float(info['format']['duration']), 1)}
            store.write_json(store.STORE / 'receipt.json', receipt)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        receipt['error'] = 'Không xử lý được tệp. Thử một GIF hoặc video ngắn ở độ phân giải thấp hơn.'
        store.write_json(store.STORE / 'receipt.json', receipt)
    finally:
        with store.lock():
            target.unlink(missing_ok=True)
            (store.STORE / 'source').unlink(missing_ok=True)
            (store.STORE / 'pending.json').unlink(missing_ok=True)


def main():
    events = DisplayEvents()
    previous = None
    conversion = None
    network = None
    with ThreadPoolExecutor(max_workers=1) as encoder:
        while True:
            if store.ready():
                if conversion and conversion.done():
                    conversion.result()
                    conversion = None
                if conversion is None:
                    pending = store.read_json(store.STORE / 'pending.json')
                    if pending:
                        conversion = encoder.submit(convert, pending)
                metrics = store.read_json(OBSERVER)
                sample = local_network()
                if sample is not None:
                    network = sample
                now = datetime.now(VIETNAM)
                scene = events.scene(metrics, network, now.timestamp(), time.monotonic())
                frame = render(metrics, network, now, scene)
                revision = hashlib.sha256(frame).hexdigest()[:20]
                if revision != previous:
                    store.replace(store.RUNTIME / 'frame.png', frame)
                    previous = revision
                source = store.status()['source']
                active = ('clip' if scene == 'summary' and source == 'clip'
                          and (store.STORE / 'clip.mp4').is_file() else 'summary')
                status = {'frame': revision, 'active': active, 'scene': scene}
                if scene in ('hotspot', 'recovered') and network:
                    status['connection'] = {'ip': network['ip'], 'name': network['name']}
                if status != store.read_json(store.RUNTIME / 'status.json'):
                    store.write_json(store.RUNTIME / 'status.json', status)
            time.sleep(5)


if __name__ == '__main__':
    main()
