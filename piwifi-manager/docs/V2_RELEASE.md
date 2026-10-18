# Dashboard V2 — 12/10/2026

Đã deploy lên Raspberry Pi 4 tại `http://192.168.1.30:18765`. Tài khoản Web được giữ nguyên.

## Giao diện

- Thay toàn bộ `rasp/` bằng tên thiết bị; logo chính thức Raspberry Pi lưu trên Pi.
- Bố cục theo ba ảnh tham chiếu: card kết nối (IP/gateway/DNS), quét Wi-Fi với cột tín hiệu và danh sách cuộn, Fallback Hotspot riêng với mật khẩu che cố định.
- Dark/light theme: lần đầu theo hệ thống; nút chuyển theme lưu vào localStorage và giữ khi reload, trên cả login và dashboard. Khi localStorage không dùng được, giao diện vẫn hoạt động trong phiên.
- Noto Sans variable WOFF2 cục bộ, hỗ trợ đầy đủ tiếng Việt; không phụ thuộc CDN. Đã kiểm tra glyph từ file font và browser font load. Tài nguyên static nằm trong payload deploy, binary được copy nguyên byte.
- CSS/JS tách riêng; telemetry mỗi 5s, trạng thái mạng mỗi 15s, polling dừng khi tab ẩn. Mask không có password plaintext phía dưới; API không đọc PSK để hiển thị.

## Fallback

- Guard và thao tác mạng qua dashboard dùng chung file lock; tác vụ recovery chờ lock có giới hạn để tránh bị bỏ qua nếu guard đang chạy.
- Wi-Fi client đang active được giữ nguyên. Khi disconnected, thử các profile infrastructure/autoconnect theo priority rồi bật AP.
- Khi AP đang hoạt động: đọc station qua iw và phiên TCP thuộc subnet AP; bất kỳ client hoặc lỗi đọc đều giữ AP. Không có client: chờ hai lần kiểm tra liên tiếp, giữ tối thiểu 120s sau khi bật AP, kiểm tra Wi-Fi đã lưu khả dụng, rồi kiểm tra client thêm lần nữa trước chuyển.
- Scan không được driver hỗ trợ hoặc không thấy Wi-Fi đã lưu: giữ AP và backoff 120s. Wi-Fi quay về thất bại: khôi phục AP và backoff.
- Chuyển profile dùng UUID và đặt recovery độc lập sau 90s khi có kết nối trước đó. Recovery kiểm tra NetworkManager connected + IPv4; target bị xóa cũng vẫn thử phục hồi kết nối trước. Đây là kiểm tra kết nối cục bộ, không bảo đảm mọi laptop truy cập được qua firewall hay Internet có hoạt động.
- Công cụ `/usr/sbin/iw` có sẵn trong PATH root trên Pi. Khảo sát trước bằng `command -v iw` trong PATH user không thấy lệnh; kết quả đó không đủ để kết luận package chưa cài. Driver `brcmfmac` đã được kiểm chứng scan được trong AP ở thử nghiệm bên dưới.

## Kiểm chứng

- 16 unittest cases đạt: API authentication, CSRF, Linux metrics, HTML Unicode/SSID escape, SSID byte limit, non-Wi-Fi rejection, lock contention, hotspot không đọc password, grace period, active-client preservation, unknown-client preservation, late-arriving client, scan error, failed return/AP restore và recovery decisions.
- HTTP đăng nhập thật, dashboard/API và CSS/JS/logo/font trả 200; response HTML UTF-8. Source không BOM, NFC; không có replacement character U+FFFD.
- Desktop light/dark đã xem trên browser; lựa chọn theme giữ sau reload; nút Chọn điền đúng SSID. Viewport 390px không tràn ngang; font tiếng Việt load thành công.
- Thử nghiệm phần cứng 17:27:04 bật Pi-Fallback; guard nhận 0 client, kiểm tra lại, rồi 17:27:15 tự về Wi-Fi `netplan-wlan0-Hoang Phuc 5G`. Có watchdog độc lập 60s đặt trước; auto-return hoàn tất trước watchdog, sau đó timer watchdog được hủy. Trong smoke test đã rút ngắn grace bằng marker test; grace 120s được kiểm tra bằng unit test.
- Chưa có thiết bị thứ hai để kiểm chứng client AP đang dùng trên phần cứng; các nhánh giữ client/late-client đã được mô phỏng. Chưa reboot/mất router thật. Không báo các trường hợp này là đã đạt kiểm thử vật lý.

Snapshot trước V2: `/var/lib/piwifi-deploy/20261012T102455-9212`. Snapshot của lần sửa cuối được ghi trong output deploy và liên kết `latest`. Rollback không đảo ngược package apt hoặc NetworkManager profiles.
Snapshot lần sửa cuối: `/var/lib/piwifi-deploy/20261012T103213-10401`. Pi vẫn kết nối Wi-Fi nhà sau deploy; guard/Web/timer hoạt động. Dữ liệu DNS đã được tách thành danh sách đầy đủ.

## Frontend-design revision — 12/10/2026

Theo yêu cầu dùng skill frontend-design: chuyển sang bố cục điều khiển thiết bị với sidebar desktop, typography/phân cấp mới, số liệu gọn hơn, card mạng theo ảnh tham chiếu và SVG cho điều hướng/quét/theme. Tablet/mobile có header và điều hướng sticky; mục điều hướng đang chọn cập nhật đúng và có aria-current. Trạng thái mạng cũ được phân biệt khi refresh thất bại. Dark/light và font cục bộ giữ nguyên.

Kiểm tra trên production: authenticated dashboard HTTP 200; ba kiểm tra render UTF-8/escape SSID, API login và CSRF đạt. Browser desktop hai theme và mobile 390px không tràn ngang, glyph tiếng Việt load thành công, điều hướng mobile hoạt động. Không thay helper/guard/NetworkManager trong revision này. Snapshot trước thay đổi: `/var/lib/piwifi-deploy/20261012T104153-11916`.

## Bố cục ít box — 12/10/2026

Người dùng muốn giảm các card/box vì bố cục trước quá giống mẫu AI. Tham khảo cách Linear giảm nhiễu bằng phân cấp nội dung và đường phân cách nhẹ: https://linear.app/now/behind-the-latest-design-refresh . Dashboard chuyển sang nền phẳng; bỏ nền/bóng/bo góc của các panel; bốn chỉ số thành một dải; các khu vực mạng và hệ thống phân chia bằng khoảng trắng/đường kẻ mảnh. Hotspot bỏ khung lồng, nút màu riêng vẫn rõ. Box chỉ còn ở form đăng nhập và các control cần tương tác. Giữ dark/light, font Việt và backend hiện tại.

Browser desktop light/dark và mobile 390px được xem trực tiếp, không tràn ngang; glyph Việt load. Đăng nhập thật dashboard HTTP 200. Bản khôi phục ổn định trước thay đổi: `/var/lib/piwifi-deploy/20261012T104820-13553`.

## Áp dụng mẫu HTML người dùng — 12/10/2026

Thay template theo file HTML người dùng gửi, với ba tab riêng (Tổng quan/Kết nối/Hệ thống & Lưu trữ), sidebar và điểm nhấn đỏ Raspberry Pi. Bỏ hoàn toàn khối hostname + “Giám sát tại chỗ / Không cần dịch vụ đám mây” trong sidebar. RAM hiển thị dung lượng thực thay badge công nghệ bộ nhớ hardcode. Giữ font Noto Sans WOFF2 cục bộ và theme sớm trước CSS; không tải font CDN từ mẫu.

Sửa tích hợp: tab theo hash, browser Back và deep-link hoạt động; theme có nút trên mobile/login; dữ liệu ổ đĩa/dịch vụ/scan nối với JS hiện tại; hotspot hiển thị ưu tiên và mask. 16 tests đạt trước deploy; browser kiểm chứng các tab, nút Quét/Chọn, light/dark và viewport 390px không overflow. Snapshot trước đổi template: `/var/lib/piwifi-deploy/20261012T105800-15495`.
