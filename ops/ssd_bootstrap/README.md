# Bộ cài mới Pi Control trên SSD

Trạng thái cập nhật 27/10/2026: Raspberry Pi OS 64-bit Desktop đã boot từ SSD;
8 module đã cài và kiểm tra hoạt động. SD cũ giữ nguyên. Xem
[biên bản chuyển SSD](STATUS_20261027.md) để biết UUID, release và phạm vi đã thử.

## Phần đã sẵn sàng

| Module | Chức năng | Cách chạy |
|---|---|---|
| network | Wi-Fi guard, timer, hotspot fallback | system service/timer riêng |
| dashboard | Web và API | system service riêng |
| observer | Tài nguyên, lượng ghi ổ OS, sự kiện chọn lọc | system service riêng |
| dns | AdGuard Home 0.107.79 ARM64, cài cấu hình mới | system service riêng |
| audio | Chọn input/output, âm lượng, Bluetooth | user agent riêng |
| media | YouTube/Spotify và Chromium riêng | user agent + browser theo nhu cầu |
| camera | Preview, ảnh timelapse, chọn vùng | user agent riêng |
| render | Ghép MP4 từ ảnh gốc | user worker riêng cho từng job |

Mỗi module có source bất biến, `current` và phiên bản trước riêng tại
`/opt/pi-control/<module>`. Cập nhật Dashboard không cập nhật hoặc restart các
dependency đã cài. CLI hỗ trợ cập nhật/quay lui từng module. Quay lui source và
unit không hoàn tác dữ liệu hoặc gói apt. Bộ cài hiện dùng contract 1, chưa có
chuyển đổi schema dữ liệu giữa các contract.

Bộ đếm ghi lấy từ toàn ổ vật lý chứa OS; khi root và data cùng SSD, ghi ảnh/video cũng được tính.

Audio hoạt động độc lập khi Media nghỉ. Camera không phụ thuộc tiến trình web.
Worker Render có giới hạn một lõi CPU và 768 MiB RAM; Camera có giới hạn 512 MiB.
Agent Camera có thể nhận lại trạng thái worker còn chạy sau khi agent restart.
Không coi đây là bảo đảm khôi phục mọi thời điểm mất điện; ảnh gốc vẫn cần kiểm tra.

Trợ giúp service đã được chuẩn bị trên trang Lưu trữ: chức năng, phạm vi system/user,
phụ thuộc, ảnh hưởng khi dừng và khi nào trạng thái inactive là bình thường.
Không thêm polling cho phần trợ giúp. Template Render và guard oneshot không bị
coi là daemon hỏng chỉ vì không chạy liên tục.

## Bộ cài và bằng chứng kiểm tra

Gói đang cài: `G:/RaspberryPI4OfTT/ops/ssd-kits/pi-control-ssd-20261027-r3.tar.gz`.
Đây là artifact tạo lại được, được bỏ qua trong Git; source bộ cài vẫn nằm trong repo.

- SHA-256 archive: `8a17fbd5961056dc3ffd4883363c1756ec3f86e1fabc5df855b6868baca9f757`.
- SHA-256 manifest: `51b2071944481311d25b4a0a308736077f4edd7f68f61d3c58121714c7addb6a`.
- 8 module, 89 file có checksum. Vendor AdGuard được kiểm tra bằng digest đã ghim;
  kèm license của upstream. Checksum giúp phát hiện gói thay đổi, không thay thế
  việc lấy source từ nơi tin cậy.
- 234 kiểm thử ứng dụng Python, 17 kiểm thử installer Linux, 7 kiểm thử layout
  và các kiểm tra Node trước đó: đạt.
- Bộ r3 đổi `dnsutils` sang gói Debian 13 `bind9-dnsutils`; manifest mới được xác minh.
- Trên Pi ARM thật, bộ r3 cài vào SSD; 8 module và 10 unit đã triển khai.
- SSH kiểm tra root `/dev/sda2` 40 GiB, data `/dev/sda3` 68 GiB đúng UUID.
- Dashboard đăng nhập HTTP 200; trang có đủ 12 mục Trợ giúp service.
- DNS AdGuard phân giải tên miền; thử từ Windows, `doubleclick.net` trả `0.0.0.0`.
- 67 log deploy SD đã nhập; tổng lịch sử hiện có 75 sự kiện, lần nhập lại thêm 0.
- Bộ kiểm thử ARM sandbox trước đó xác minh cấu hình AdGuard và 10 systemd unit;
  đây là bằng chứng cài đặt thử, không thay cho thử reboot/dài hạn trên SSD.

Chưa nghiệm thu: ổn định USB/nguồn dài hạn, reboot, khôi phục Wi-Fi khi mất mạng
hoặc AP có client, Spotify thật, thiết bị Bluetooth, webcam/ghi/ghép dài và iPhone.

## Hệ thống đã boot từ SSD

OS, hostname `raspberrypi`, user `thinh` và Wi-Fi được cấu hình bằng Imager.
SSH host key mới đã xác minh từ console; public key máy Windows đã cài.
Không clone hoặc phục hồi OS/cấu hình cũ. Chỉ 67 sự kiện deploy đã lưu được nhập
vào lịch sử mới, đánh dấu là lịch sử SD và không có rollback.

## Layout SSD đang chạy

| Vùng | Dung lượng | Định dạng / vai trò |
|---|---:|---|
| boot | Khoảng 512 MiB | FAT32, theo image thực tế |
| root `/` | 40 GiB | ext4, OS/gói/phần mềm/cấu hình và trạng thái nhỏ |
| data `/srv/pi-control` | 68 GiB | ext4, ảnh/video và dữ liệu lớn |
| phần còn lại | Khoảng 10,7 GiB | Chưa phân vùng |

Dung lượng thực 128 GB khoảng 119,2 GiB. Khoảng 10,7 GiB chưa phân vùng.
SMART mới đọc: Percentage Used 31%, Critical Warning 0, Spare 100%, Media Errors 0,
Error Log Entries 7.274, nhiệt độ mẫu 51°C. Đây là chỉ số bộ điều khiển; không
quy đổi thành phần trăm thời gian còn lại.

Data mount theo UUID ở `/srv/pi-control`; Camera từ chối ghi nếu SSD data mất.
Thẻ SD giữ nguyên OS cũ, vai trò dài hạn còn thảo luận.

## Quản lý sau khi cài

Source lần cài đầu r3 ở `/opt/pi-control-bootstrap-r3`; bản tối ưu Dashboard và
Observer r4 đã cài ngày28/10/2026 từ `/opt/pi-control-bootstrap-20261028-r4`.
Media và Dashboard sau đó được cập nhật từ `/opt/pi-control-bootstrap-20261028-r5e`;
Observer giữ r4, năm module còn lại giữ release r3. Xem
[báo cáo rà soát](../../pi-control/docs/AUDIT_20261028.md) và
[Media r5](../../pi-control/docs/MEDIA_R5.md).
Cấu hình runtime tại
`/etc/pi-control/runtime.json` giữ UUID/generation/user, không có mật khẩu.
Kế hoạch chỉ đọc. Khi tạo gói cập nhật mới, xác minh manifest rồi chỉ cập nhật
module cần thiết; ví dụ Dashboard:

```sh
sudo python3 -B /opt/pi-control-bootstrap-20261028-r5e/bootstrap.py install \
  --config /etc/pi-control/runtime.json --modules dashboard --apply
sudo python3 -B /opt/pi-control-bootstrap-20261028-r5e/bootstrap.py rollback \
  --config /etc/pi-control/runtime.json --modules dashboard --apply
```

Bộ cài từ chối SD, hệ thống legacy, UUID sai, root/data khác ổ và ổ ngoài khoảng
128 GB. `install` thiếu `--apply` chỉ lập kế hoạch. `--root` chỉ dành cho thử.

Chỉ cài gói apt còn thiếu; không chạy nâng cấp toàn hệ thống. Installer chỉ cấp
NOPASSWD cho helper có lệnh cố định, không cấp quyền sudo chung. Network tạo
profile fallback mới nhưng không tự kích hoạt hoặc ngắt Wi-Fi hiện tại.

Media mặc định nghỉ, đăng nhập lại trực tiếp nếu cần; không copy cookies/keyring.
Chỉ browser Media dùng `password-store=basic` theo lựa chọn trước đây; không sửa
keyring hệ thống. Chính sách uBlock Origin Lite được cài mới, extension cần tải
và kiểm tra sau khi browser chạy; chưa hứa hiệu quả chặn quảng cáo thực tế.
AdGuard dùng mật khẩu mới, DHCP tắt, query log/thống kê trong RAM. Giao diện quản
trị AdGuard chỉ nghe loopback; sử dụng SSH forwarding để truy cập từ Windows.
Journald được cấu hình RAM 64 MiB cho lần boot sau; các sự kiện chọn lọc và lượng
ghi ổ OS vẫn lưu có giới hạn như tính năng đã được yêu cầu. Không cần chồng thêm
log2ram trong bộ cài mới mặc định.

Mỗi gói mới cần source/recipe hash mới. Camera/Render từ chối cập nhật khi đang
ghi/ghép hoặc không kiểm tra được trạng thái. Quay lui chỉ đổi source/unit, không
khôi phục dữ liệu hay gói apt. Không tự xóa release/dữ liệu. Lịch sử SD là
`historical_only`, không tạo rollback OS. Lệnh Deploy legacy được chặn trên
hệ thống modular.

Mật khẩu Dashboard được chép vào clipboard bằng `./ops/pi-control.ps1 -Action
Password -Address 192.168.1.30`; trên modular host thao tác này đọc file root-only
bằng quyền sudo tạm. Username là `admin`. Dashboard LAN: `http://192.168.1.30:18765`.
Mật khẩu hotspot fallback có thể chép bằng nút `Chép mật khẩu Wi-Fi dự phòng`;
cấp quyền sudo tạm trước nếu thao tác báo hết hạn.
AdGuard admin chỉ nghe loopback; DNS lọc đã được thử từ Windows. Cloudflare Tunnel
đã nhận token mới, tự chạy và truy cập HTTPS qua hostname được; Access policy chưa
xác minh. EdgeVision Robot dùng repo/bộ cài riêng và cần phối hợp quyền
webcam. Không mặc định thêm Tailscale. Preset EasyEffects và đăng nhập Spotify cần
thiết lập/nghe thử lại trực tiếp trên Pi.

Journald cấu hình RAM 64 MiB; nhật ký chọn lọc và thống kê ghi OS lưu theo giới hạn
đã thiết kế. Không thêm log2ram chồng lên trong bộ cài mới.

## SD: các phương án còn đang thảo luận

| Phương án | Giá trị | Giới hạn |
|---|---|---|
| Giữ nguyên SD hiện tại, tháo cất sau khi SSD ổn | Có OS cũ để boot thủ công khi cần | Cấu hình/dữ liệu mới trên SSD không tự đồng bộ về SD |
| SD cứu hộ tối giản | SSH, kiểm tra SMART/USB, mount SSD, sửa filesystem offline | Cần chuẩn bị và thử boot riêng; không tự phục hồi SSD hỏng vật lý |
| SD làm OS thử nghiệm | Thử phần mềm/robot mà không sửa OS chính | Chỉ một OS chạy trên cùng Pi ở một thời điểm |
| SD làm ổ dữ liệu phụ | Tận dụng thêm dung lượng | Vẫn chịu hao mòn; không phù hợp ghi log/video liên tục |
| SD boot, SSD chứa root | Dùng khi USB boot có vấn đề | Vẫn phụ thuộc SD; không đạt mục tiêu SSD boot độc lập |
| Chuyển sang SD tự động khi SSD lỗi | Có thể hữu ích cho lỗi boot cụ thể | Boot order không xử lý mọi lỗi root/I/O/USB treo; cần watchdog, cấu hình và thử lỗi riêng |

Đề xuất hiện tại: giữ nguyên SD trong thời gian chuyển đổi. Khi SSD đã nghiệm
thu, bàn tiếp giữa cất SD cũ và làm SD cứu hộ tối giản. Chưa chọn hay format SD.
Cấu hình EEPROM chưa có BOOT_ORDER tuỳ chỉnh; mặc định Pi thử SD trước rồi USB.
Vì vậy, để khởi động SSD phải tháo SD; nếu cắm lại SD rồi reboot, máy có thể vào
OS cũ trước. Cắm cả hai không chạy hai OS song song. Khi một OS boot, ổ còn lại
chỉ là storage nếu được mount. Chưa thử lỗi để xác nhận automatic failover.

## Tạo lại gói

```powershell
python -B ops/ssd_bootstrap/build.py ops/ssd-kits/<new-output-directory>
```

Nguồn lấy từ allowlist của `service_catalog.json`, không từ filesystem live.
Không đưa `.env`, SSH key, cookies, cơ sở dữ liệu hoặc hồ sơ đăng nhập vào gói.
Kiểm thử ARM staging bằng `verify_staged.py`, chỉ trỏ tới gói trong thư mục thử.

Tài liệu tham chiếu: [cài OS chính thức](https://www.raspberrypi.com/documentation/computers/getting-started.html),
[USB boot](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#usb-mass-storage-boot),
[resize_early của image trixie](https://github.com/RPi-Distro/raspberrypi-sys-mods/blob/pios/trixie/initramfs-tools/scripts/local-premount/resize_early).
