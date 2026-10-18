# Raspberry Pi Dashboard

Dashboard tổng hợp nhiệt độ, CPU/RAM, swap, uptime, dung lượng ổ đĩa và trạng thái dịch vụ, kết hợp quản lý Wi-Fi. Xem `docs/DASHBOARD.md` để biết cơ chế guard, phục hồi và phạm vi kiểm chứng.

Web UI quản lý Wi-Fi cho Raspberry Pi 4 chạy Debian 13 / Raspberry Pi OS với NetworkManager.

## Kiến trúc

```text
Browser
  -> Gunicorn :18765
  -> Flask app (/opt/piwifi-web)
  -> sudo /usr/local/sbin/piwifi-helper
  -> nmcli
  -> NetworkManager
  -> wlan0
```

Web app chạy bằng user thường (`thinh` theo cấu hình hiện tại). Chỉ helper nhỏ, root-owned, được phép chạy qua sudo để thay đổi NetworkManager.

## Cấu trúc source

```text
piwifi-manager/
├── app.py
├── templates/index.html
├── helper/piwifi-helper
├── systemd/piwifi-web.service
├── sudoers/piwifi-web
├── config/piwifi-web.env.example
├── scripts/install.sh
├── scripts/uninstall.sh
├── requirements.txt
└── docs/STRUCTURE.md
```

## Vị trí khi deploy

- `/opt/piwifi-web/` - mã ứng dụng Web.
- `/usr/local/sbin/piwifi-helper` - helper quản trị mạng cần quyền root.
- `/etc/piwifi-web.env` - username/password Web UI và Flask secret.
- `/etc/sudoers.d/piwifi-web` - quyền sudo giới hạn cho helper.
- `/etc/systemd/system/piwifi-web.service` - service tự chạy khi boot.

## Triển khai từ workspace Windows

```powershell
# Tại G:\RaspberryPI4OfTT
.\ops\pi.ps1 -Action Authorize
.\ops\pi.ps1 -Action Deploy
```

Deploy chuẩn bị release đầy đủ, tạo snapshot rồi chuyển symlink và restart dịch vụ. Installer không chạy riêng. Xem `docs/V31_RELEASE.md` cho bố cục release, SQLite và kiểm chứng rollback.

Mở:

```text
http://raspberrypi.local:18765
```

hoặc IP hiện tại của Pi.

Khi Pi đang ở fallback Hotspot:

```text
http://192.168.50.1:18765
```

## Lệnh kiểm tra

```bash
sudo /usr/local/sbin/piwifi-helper status
sudo /usr/local/sbin/piwifi-helper scan
systemctl status piwifi-web --no-pager
journalctl -u piwifi-web -n 100 --no-pager
sudo ss -ltnp | grep 18765
nmcli connection show
```

## Phát triển

Chạy Flask trực tiếp để debug:

```bash
cd /opt/piwifi-web
set -a
source /etc/piwifi-web.env
set +a
python3 app.py
```

Production dùng Gunicorn qua systemd.

## Lưu ý an toàn

- Không commit `/etc/piwifi-web.env` hoặc mật khẩu Wi-Fi lên Git.
- `piwifi-helper` phải do `root:root` sở hữu và không cho user thường sửa.
- Web UI hiện dùng HTTP trong LAN/Hotspot. Nếu expose ra Internet, phải đặt reverse proxy HTTPS + firewall/VPN.
- Chuyển profile Wi-Fi trên cùng `wlan0` sẽ làm HTTP/SSH/VNC hiện tại rớt; đây là hành vi bình thường.
