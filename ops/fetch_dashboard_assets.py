"""Fetch upstream assets once; runtime serves only local files."""
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1] / 'pi-control/static'
for name, url in {
    'raspberry-pi.png': 'https://www.raspberrypi.com/app/uploads/2022/02/COLOUR-Raspberry-Pi-Symbol-Registered.png',
    'fonts/noto-sans.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf',
    'fonts/OFL.txt': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/OFL.txt',
}.items():
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.raspberrypi.com/trademark-rules/'})
    with urllib.request.urlopen(request, timeout=60) as r:
        p.write_bytes(r.read())
    print(name, p.stat().st_size)

# Build-time packages only: fonttools and brotli. Neither is needed on the Pi.
from fontTools.ttLib import TTFont
p=root/'fonts/noto-sans.ttf'
font=TTFont(p)
sample='Nhiệt độ Địa chỉ IP Ưu tiên Đang kết nối Bộ nhớ Ổ đĩa Khôi phục Ắ ằ ễ ộ ự Đ đ'
assert all(ord(c) in font.getBestCmap() for c in sample if not c.isspace())
font.flavor='woff2'
font.save(p.with_suffix('.woff2'))
p.unlink()
