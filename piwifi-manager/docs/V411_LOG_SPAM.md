# 4.1.1 — Gộp log lặp

Đã triển khai release/snapshot `20261026T101249-15826`.

Journalctl dùng --grep với -n trả kết quả từ mới về cũ. Bộ gộp trước đây yêu cầu
thời gian tăng dần nên một đợt lỗi thành nhiều dòng và cursor có thể quay về bản
cũ. Ingest nay sắp xếp tăng dần, giữ cursor mới nhất bằng cursor_at. Bản đến trễ
không ghi đè chi tiết mới nhất, vẫn cập nhật thời điểm đầu và số lần.

Lỗi cùng thiết bị/dịch vụ, loại lỗi, mức độ và boot được gộp nếu khoảng cách
không quá 5 phút. Tách DNS, kết nối máy chủ, kết nối Dashboard và EOF của Tunnel.
Chỉ bỏ thông báo cloudflared “Incoming request ended abruptly: context canceled”
do đóng luồng xem; lỗi timeout thật, mất USB/I/O và lỗi dịch vụ khác vẫn giữ.
User unit được phân biệt với user@1000.service. Không coi ngắt USB là ổ hỏng:
người dùng xác nhận chủ động rút SSD lúc 14:09:25 ngày 25/10 để sao lưu.

Kho cũ được gộp một lần trong RAM khi load, giữ tổng count/thời điểm đầu-cuối,
cursor và seenIDs; checkpoint grouping=2 theo lịch dirty-only 60 giây hiện có.
Không compact/ghi từ GET. Bản sao trước chuyển đổi0600:
`/var/lib/piwifi-observer/system-events-before-v411-20261026T101246Z.json`.
Không tự phục hồi tệp này khi rollback nguồn vì sẽ bỏ các sự kiện mới hơn.

198 kiểm thử Python và Node UI/polling đã qua. Mẫu cũ391 dòng còn79, lọc42
lần hủy luồng bình thường; tổng count còn lại được bảo toàn. Dữ liệu production
sau deploy113 nhóm, API gồm cả lịch sử quản trị226 dòng; số liệu thay đổi khi
có sự kiện mới. Không thay polling, retention, checkpoint hoặc sửa filesystem.
