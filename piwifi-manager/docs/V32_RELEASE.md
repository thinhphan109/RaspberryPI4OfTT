# Dashboard 3.2 — nguồn, GPIO, SSH và lịch sử RAM

Triển khai ngày 14/10/2026 lên Pi 4 Model B Rev 1.5, Debian 13.7 aarch64.
Release: `/opt/piwifi-releases/20261014T051814-11395`.
Snapshot phục hồi: `/var/lib/piwifi-deploy/20261014T051814-11395`.

## Thay đổi

- Nguồn: đủ cờ hiện tại bit 0..3 và lịch sử bit 16..19; badge tổng quan, chi tiết, trạng thái unknown khi thiếu công cụ. Xung CPU đọc sysfs.
- Băng thông: biểu đồ SVG RX/TX 30 mẫu, giới hạn sessionStorage, định dạng B/s–KiB/s–MiB/s, theo boot/interface. Reset bộ đếm không tạo spike; tổng là bộ đếm interface, không phải dung lượng lifetime. Dùng tuyến mặc định chọn interface, fallback wlan0 khi không có tuyến.
- GPIO: sơ đồ 40 chân vật lý, filter và inspector; đọc pinctrl một lần cho BCM0..27, cache10s. Không claim line, không đổi pull/direction/output. API control luôn từ chối; auth/CSRF vẫn kiểm tra. Không cấp quyền mới.
- SSH: kết nối TCP và đăng nhập thành công được đặt tên riêng. Đọc journal JSON tối đa200 record, cursor RAM, cache60s; số lần password/publickey thất bại là số đã quan sát, không khẳng định đủ24h. Không mở rộng thời gian lưu journal. Cổng thực tế Pi là22.
- RAM: observer giữ tối đa10080 mẫu phút và500 sự kiện sức khỏe; snapshot /run và Unix socket600 phục vụ web/MCP. Kiểm tra /run tmpfs trước khởi chạy. Các GET lịch sử không mở SQLite; DB cũ không bị xóa.
- Tầng nhanh API đọc /proc và /sys, tính CPU/RX/TX dựa vào baseline observer, không sinh subprocess hay cập nhật baseline theo từng browser. Nguồn10s, service60s, trạng thái mạng60s và processes30s có cache. Thu thập vẫn10s; không có write telemetry lên SD.
- Gunicorn bỏ access log; không spam lỗi observer mỗi vòng. PYTHONDONTWRITEBYTECODE cho web/observer. Các tác vụ deploy và thay cấu hình vẫn ghi bền vững có chủ đích.
- JS clear timer khi hidden, GPIO chỉ poll đúng tab; events/history/deployments chỉ đúng view. Font JetBrains Mono và giấy phép bundled, Noto Sans cho tiếng Việt; SVG, không CDN. Quạt được bỏ qua theo yêu cầu.
- Workflow thêm `-Address` để xử lý mDNS lỗi, vẫn dùng key/host fingerprint đã xác minh. Không thay Wi-Fi profile, desktop, tunnel, boot config, swap hoặc sudoers.

## Đánh đổi và giới hạn

- Restart observer/deploy/reboot làm mất lịch sử RAM mới. Lịch sử vẫn thu thập khi đóng trình duyệt.
- Zram có backing device loop0 trên Pi; tmpfs/RAM không đồng nghĩa tuyệt đối không thể ghi SD nếu memory pressure dẫn đến writeback. Audit hiện tại swap used0; không tự tắt swap.
- Các event thao tác quản trị và thay đổi fallback có chủ đích tiếp tục được lưu bởi helper hiện có. Zero-write áp dụng cho polling và telemetry mới, không phải mọi dịch vụ Linux.
- Chỉ thử phần cứng Pi4; Pi3/Pi5 chưa có kiểm chứng thực tế. Pinout chung có thể tra cứu nhưng không bảo đảm các alternate functions/driver trên model khác.
- Các thử nghiệm physical outage, boot không có mạng quen và AP client vẫn chưa thực hiện trong đợt này.

## Kiểm chứng

- 41 unittest Linux đạt; kiểm thử Node.js lifecycle timer overview/hidden/resume/network/leave đạt. Bộ test Linux: hồi quy Wi-Fi/CSRF/operation/cache, power flags, GPIO mapping/parser/disabled control, SSH IPv6, RAM history và fast metrics không subprocess.
- Python AST, JS syntax và payload DryRun đạt.
- Deploy, rollback về bản cũ và deploy lại thành công; web/observer/guard active. DB cũ giữ nguyên.
- Production qua rasp4.thinhme.tech: nguồn, GPIO, SSH và băng thông hiển thị; không thấy lỗi JS của app. Tổng quan chỉ poll metrics. Preview390px: light/dark,40pins, không tràn ngang; viewport override đã reset.
- Bài đo đầu604,4s: CPU1,252% toàn Pi, process write_bytes12288, DB cũ không đổi. Đã sửa helper dùng python -B để tránh bytecode khi sudo xóa biến môi trường, giảm chẩn đoán xuống một nmcli đọc connection/IP/gateway và tăng cache network60s (xóa ngay khi thao tác mạng). Bài đo bản cuối604,4s: CPU1,734% một core, tương đương0,433% toàn Pi4core; web/observer write_bytes tăng0, SQLite cũ không đổi, toàn host SD ghi102400byte và có11mẫu lịch sử RAM. Cgroup CPU bao gồm tiến trình con; counter I/O của parent và các process dịch vụ được kiểm tra, zram bd_stat0. Phạm vi đo: một client, năm client và polling GPIO, thêm kiểm tra trình duyệt thực. Không bảo đảm toàn host zero-write hay mọi workload tương lai đều dưới1%.

## Phục hồi

`./ops/pi.ps1 -Action Rollback -Address <IP-thực-tế>` sử dụng snapshot đầy đủ release và unit. Socket nằm trong /run; không thêm unit mới nên restore sẽ dừng observer mới trước phục hồi bản cũ. Nếu rollback về3.1, observer sẽ ghi SQLite lại theo chính sách của bản đó; đây là lý do cần kiểm tra version sau rollback.

Tool tái đo: `ops/verify-upgrade.py`, chạy trực tiếp trên Pi bằng sudo tạm. Tool dùng secret ứng dụng trong RAM để kiểm tra HTTP authenticated, không in thông tin đăng nhập. Báo CPU cgroup gồm process con; I/O process và counter SD toàn host được tách riêng.
