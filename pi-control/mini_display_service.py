"""Render the mini display in RAM and prepare uploaded clips for playback."""

from datetime import datetime
from functools import lru_cache
import hashlib
from io import BytesIO
import json
from pathlib import Path
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
CAT = None
VIETNAM = ZoneInfo('Asia/Ho_Chi_Minh')


@lru_cache(maxsize=24)
def typeface(face, size):
    return ImageFont.truetype(face, size)


def local_network():
    try:
        links = json.loads(subprocess.check_output(
            ['/usr/sbin/ip', '-j', '-4', 'address', 'show', 'up', 'scope', 'global'], timeout=2))
        links.sort(key=lambda link: link['ifname'] != 'wlan0')
        for link in links:
            addresses = link.get('addr_info', [])
            if addresses:
                interface = link['ifname']
                try:
                    name = subprocess.check_output(
                        ['/usr/bin/nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', interface],
                        text=True, timeout=2, stderr=subprocess.DEVNULL).strip()
                except (OSError, subprocess.SubprocessError):
                    name = ''
                return addresses[0]['local'], name if name not in ('', '--') else interface, interface
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return 'Chưa có IP', 'Chưa kết nối', ''


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


def render(metrics, network, now):
    ip, ssid, interface = network
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
    stale = time.time() - metrics.get('timestamp', 0) > 45
    hot = isinstance(temperature, (int, float)) and temperature >= 80
    status = ('Dữ liệu cũ' if stale else 'Nguồn yếu' if power.get('undervoltage')
              else 'Nhiệt độ cao' if hot else 'Đang giảm xung' if power.get('throttled')
              else 'Tổng quan')
    tone = amber if status != 'Tổng quan' else mint
    label(now.strftime('%H:%M'), 16, 13, 14, ink, MONO)
    label(status, 71, 14, 12, tone, width=145)
    label(now.strftime('%d/%m/%Y'), 225, 14, 12, muted, MONO, 79)
    draw.line((16, 35, 303, 35), fill=line)
    frame.paste(CAT, (220, 39), CAT)
    label('Nhiệt độ SoC', 16, 48, 13)
    label(number(temperature, '°C'), 13, 67, 46, amber if hot else ink, MONO, 187)
    meter(16, 116, temperature, 85, 178, amber if hot else mint)
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
    global CAT
    with Image.open(ASSETS / 'mini-cat/network.png') as sprite:
        CAT = sprite.convert('RGBA').resize((87, 87), Image.Resampling.LANCZOS)
    previous = None
    while True:
        if store.ready():
            pending = store.read_json(store.STORE / 'pending.json')
            metrics = store.read_json(OBSERVER)
            frame = render(metrics, local_network(), datetime.now(VIETNAM))
            revision = hashlib.sha256(frame).hexdigest()[:20]
            if revision != previous:
                store.replace(store.RUNTIME / 'frame.png', frame)
                previous = revision
            source = store.status()['source']
            active = source if source == 'clip' and (store.STORE / 'clip.mp4').is_file() else 'summary'
            status = {'frame': revision, 'active': active}
            if status != store.read_json(store.RUNTIME / 'status.json'):
                store.write_json(store.RUNTIME / 'status.json', status)
            if pending:
                convert(pending)
                continue
        time.sleep(5)


if __name__ == '__main__':
    main()
