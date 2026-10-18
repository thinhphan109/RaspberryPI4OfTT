# Dashboard 3.12 — lượng ghi SD có lưu lịch sử

## Phạm vi và lưu trữ

Theo yêu cầu ngày19/10/2026, thống kê ghi SD là ngoại lệ có chủ đích đối với
chính sách telemetry RAM-only của3.2. CPU/RAM/nhiệt độ/mạng và các lịch sử cũ
vẫn giữ chính sách hiện tại. Không chuyển tất cả polling sang SQLite.

- Lấy mẫu bộ đếm hoàn thành ghi `/sys/block/mmcblk0/stat` mỗi10giây trong observer.
  Một sector ở bộ đếm này là512byte, độc lập block size của filesystem.
- Lưu SQLite riêng `/var/lib/piwifi-observer/storage-writes.db`, trong StateDirectory
  hiện có, DB0600. Mã nguồn root-owned; không thêm sudoers hoặc quyền mới.
- Chỉ observer ghi DB; GET Dashboard đọc qua socket hiện có, không mở writer mới.
  Connection giữ mở, transaction atomic/FULL; không checkpoint theo từng request.
- Lưu gộp300giây/lần, lưu mốc đầu tiên và lưu cuối khi dừng dịch vụ bình thường.
  Khi checkpoint lỗi, giữ pending trong RAM và chờ chu kỳ retry tiếp theo.
- Dữ liệu phút giữ7ngày, dữ liệu giờ giữ90ngày. Tổng tích lũy và dữ liệu theo ngày
  không tự xóa; ngày theo timezone Việt Nam. Đồ thị trả tối đa360điểm, có thể gộp
  nhiều ngày vào một cột khi chọn Toàn bộ. DB vẫn giữ từng ngày gốc.

## Ý nghĩa và tính liên tục

- **Từ lần khởi động này**: bộ đếm kernel của thiết bị.
- **Tổng từ lúc theo dõi**: cộng các chênh lệch quan sát từ mốc kích hoạt tính năng.
  Không tự cộng lượng ghi trước mốc đó; không gọi đây là số liệu suốt đời thẻ.
- Lưu baseline cùng total trong một transaction để tránh cộng trùng sau restart.
  Cùng boot có thể bắt kịp chênh lệch kể từ checkpoint cuối. Boot mới cộng bộ đếm
  mới từ0. Reset counter trong cùng boot không tạo số âm hoặc spike.
- Hash CID phân biệt thẻ: tổng của các thẻ không trộn nhau. Không trả CID lên web.
  Dữ liệu nằm ngoài release, deploy/rollback mã nguồn không xóa thống kê.
- Nếu mất điện/kill đột ngột rồi reboot, phần cuối boot cũ chưa checkpoint có thể
  mất khoảng tối đa5phút khi lưu đang hoạt động bình thường; nếu DB lỗi, thiếu hụt
  có thể dài hơn và giao diện báo lỗi. Không hứa chính xác tuyệt đối khi mất điện.
- Khoảng quan sát bắc qua biên phút/giờ/ngày được phân bổ theo thời gian, nên
  tốc độ và lượng mỗi khoảng là ước tính trung bình. Lấy mẫu bị gián đoạn không
  được hiển thị như tốc độ tức thời mới. Tổng chênh lệch vẫn được cộng đầy đủ.
- Không đọc được trước khi tính năng hoạt động; báo cáo audit cũ không đủ dữ liệu
  để dựng lại lịch sử ngày. Không dùng ext4 lifetime làm tổng ghi của cả thẻ.

## UI và kiểm chứng trước triển khai

Khối luôn hiển thị trong Lưu trữ: tốc độ hiện tại, bộ đếm boot, tổng tích lũy,
mốc bắt đầu/đã lưu, đồ thị tốc độ màu cam và cột lượng ghi màu xanh có trục số.
Polling10giây chỉ khi tab Lưu trữ đang hiển thị. Không có nút xóa/reset/sửa thẻ.

123Python tests qua trên Pi trong staging, gồm17test mới về baseline, restart,
crash cùng boot, boot mới, counter reset, đổi thẻ, biên ngày Việt Nam, retention,
đọc không ghi, checkpoint batching, lỗiSQLite, APIauth/range và giới hạn đồ thị.
JavaScript syntax, kiểm thử lifecycle polling và Deploy DryRun qua.

## Triển khai và kiểm tra trực tiếp

Release/snapshot: `20261018T172929-310672`, triển khai theo giờ Việt Nam ngày19/10.
DB mới có quyền0600, sở hữu thinh, dung lượng ban đầu20KiB. Web/observer/guard,
AdGuard và tunnel đều active. Không thay đổi hồ sơ Wi-Fi hoặc cấu hình âm thanh.

Đọc qua socket lặp lại trong20giây không đổi mtimeDB. Khởi động lại observer thật
đã giữ nguyên started, tổng không giảm (8.187.904 ->8.294.400byte vì host tiếp tục
ghi) và giữ điểm đồ thị ngày. Graceful shutdown đã flush. Lịch sử CPU/RAM khác
vẫn là RAM và mất sau restart như chính sách cũ.

Dashboard production có dữ liệu thật, trục số, đường tốc độ cam/cột dung lượng
xanh; đã thử7ngày/Toàn bộ và trả lại24giờ/30ngày. Kiểm tra390/1366/1920px không
tràn ngang; viewport trả về mặc định, nền đen giữ nguyên. Chưa thử iPhone vật lý
hay reboot/cúp điện thật. Xử lý boot mới và checkpoint300giây được xác minh bằng
unit test; chưa có phép đo production đủ300giây trong đợt triển khai này.

Thêm `storage_writes.py` và `static/storage-writes.js` vào installer/allowlist;
Python mới cũng phải nằm trong AST checks của runner.

Nguồn định nghĩa bộ đếm: https://docs.kernel.org/block/stat.html
