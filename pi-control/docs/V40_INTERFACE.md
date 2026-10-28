# Pi Control 4.0.1 — Giao diện và phân cấp thông tin

Yêu cầu: thiết kế lại toàn bộ Dashboard, giảm ghi chú hiển thị thường trực và
cải thiện thao tác. Giữ nền đen trung tính, biểu đồ nhiều màu và các nhóm chức
năng mở trực tiếp. Không đưa các nhóm thao tác trở lại accordion.

## Bố cục và ngôn ngữ

- Điều hướng ngắn, icon riêng cho Camera/Âm thanh, trạng thái trang hiện tại rõ.
- Mỗi trang có một tiêu đề, mô tả ngắn và nút Trợ giúp theo đúng nội dung trang.
- Sidebar216px, content tối đa1660px; grid dùng minmax(0,1fr), không zoom/scale.
  Mobile chuyển sang điều hướng ngang; Media một cột ở≤900px, form mobile16px.
- Nền tối#09090b, card#121214. Accent thao tác xanh; cảnh báo/lỗi/thành công có
  chữ và màu riêng. Light mode dùng nền trung tính và cùng hệ thành phần.
- `studio.css` là lớp bố cục thống nhất trên primitives `dashboard.css`, thay
  các lớp ghi đè thiết kế cũ. GPIO giữ nguyên minh họa2×20, cỡ nhãn, ánh xạ40
  chân và8màu; chỉ cuộn bên trong sơ đồ. Giữ nhãn trục, màu, nét và tooltip chart.
- Tổng quan ưu tiên4chỉ số trước điều khiển giảm tải. Media đưa chọn nội dung và
  hẹn giờ cạnh player; chống lặp/giới hạn/hàng đợi hiện ngay bên dưới. Camera chỉ
  hiện thao tác hiệu chỉnh khi chọn Theo vị trí, đồng bộ mode phiên đang ghi
  từ server khi mở bằng tab khác. Không tự đổi cấu hình camera.

## Hướng dẫn, trạng thái và kết quả thao tác

`templates/help.html` chứa9chủ đề trong dialog Trợ giúp. Hướng dẫn DNS iPhone,
giới hạn bộ nhớ, cách hiệu chỉnh A1, semantics lịch sử/rollback chuyển vào đây.
Các cảnh báo đang xảy ra, lựa chọn nơi lưu và trạng thái ghi vẫn hiển thị tại
khối liên quan. Nút cài DNS iPhone mở đúng chủ đề, không thêm trang điều hướng.

`static/interface.js` cung cấp PiUI.feedback:

- Thành công tự ẩn sau5giây; render lại cùng message không kéo dài timeout.
- Lỗi giữ đến khi đóng hoặc xử lý thành công; không dùng success ghi đè lỗi
  được trả trong một HTTP200. Poll Audio thành công không xóa lỗi thao tác.
- Có nút đóng, dùng textContent, aria status/alert. Không chèn HTML từ message.
- Dialog native có tiêu đề, Đóng/Escape, focus trở lại trigger. Skip link đưa
  focus vào main mà không đổi route. Pagehide dọn timeout và thông báo tạm.
- Không thêm API, interval, observer hoặc ghi cấu hình để phục vụ giao diện.

Các ID điều khiển, form POST/CSRF, API, lịch polling và chính sách Media/DNS/
Wi-Fi/GPIO được giữ. Bao gồm help.html/interface.js trong installer và allowlist
ops/pi.ps1; interface.js tải trước các module trang. CI thêm Node interface và
feedback checks. Assets dùng version theo thư mục release để tránh cache cũ.

## Sửa lỗi camera đi kèm

Người dùng báo `broken data stream when reading image file` làm phiên Position
dừng. Bản3.14.4 tách lỗi giải mã JPEG: bỏ khung lỗi/reset ổn định, giữ phiên;
Interval chỉ giải mã khi đến hạn ghi. Không bật đọc ảnh bị cắt hoặc sửa ảnh giả.
Xem `V3144_CAMERA_JPEG.md`. Lỗi ổ lưu, giới hạn và mất webcam vẫn dừng ghi.

Trong kiểm tra cuối phát hiện cảnh báo timeout sai khi tự nghỉ: disable xóa
frame_at trong lúc SIGTERM chưa hoàn tất, watchdog hiểu nhầm mất ảnh.4.0.1 thêm
closing và check_stream; chỉ kiểm tra timeout khi capture không đang đóng chủ
động. Unit test giữ cả hai nhánh: nghỉ không báo lỗi, mất ảnh thật vẫn dừng một
lần. Không thay TTL/grace hoặc cách giữ webcam trong phiên ghi.

## Kết quả kiểm tra và giới hạn

166Python tests qua. Node camera/gallery, interface, feedback, polling, charts,
Nonstop và syntax đều qua. Source contract:157ID gốc và11định nghĩa form được
giữ; NFC, CSS cân bằng, không zoom/scale, màu/ánh xạ GPIO và chart vẫn có.

Production HTTP có đăng nhập:9view/nav/help khớp,207ID duy nhất, một h1 mỗi view,
POST form cóCSRF, không đặt control trong details, modal labels/skip link đúng,
14JS/CSS đềuHTTP200. Gallery đọc/tải JPEG SSD byte-identical, auth/index/session/
headers/storage preference đúng. Lúc đầu thư viện trống; sau phiên mới của người
dùng có1ảnh nên kiểm tra gallery thật đã thực hiện lại với phiên đó.
Thử idle bằng HTTP có đăng nhập và webcam thật: lease bật capture, hình ổn định
qua12giây, release người xem cuối rồi FFmpeg tắt sau grace, error rỗng. Không
ghi phiên mới hoặc đổi calibration/storage để thực hiện phép thử này. Cuối
kiểm tra camera nghỉ, không ghi/ghép;6dịch vụ web/observer/guard/AdGuard/camera/
Media active. Phiên Position mới đã chạy quá79giây mà không lỗi decoder ở lần
quan sát, nhưng chưa có bằng chứng một ảnh đúng mỗi lớp hoặc chạy dài hạn.

Bản xem thử desktop Tổng quan/Media đã được quan sát trước chỉnh spacing cuối.
Lần tiếp tục, công cụ trình duyệt chặn truy cập localhost; không thử đường vòng.
Do đó chưa xác minh trực quan bản cuối đủ9trang/viewport mobile/light hoặc iPhone
thật. Kiểm tra cấu trúc/HTTP không thay thế kiểm tra hình ảnh. Không tuyên bố
đã qua mọi kích thước. Có thể cần chỉnh thêm sau phản hồi trên thiết bị thực.

Các deploy kiểm tra trạng thái camera trước: một lần bị chặn do phiên đang ghi,
chỉ deploy tiếp sau người dùng kết thúc và ghép xong. Không ngắt phiên để test.
Final release/snapshot: `20261024T151517-196876`, version4.0.1. Snapshot root-only
theo retention5bản. Bản xem thử chỉ loopback và không điều khiển camera/Media;
cleanup staging/server/tunnel sau kiểm tra. Source rollback không xóa video,
đổi mount SSD, DNS client hay trạng thái Bluetooth.

## 4.0.2 — Khôi phục chiều rộng biểu đồ ghi SD

Ảnh người dùng gửi sau4.0.1 cho thấy hai đồ thị chỉ chiếm phần trái card. Lớp
studio.css mới giữ height nhưng thiếu width/display của storage-write-chart,
khiến SVG dùng intrinsicwidth300px. Đã khôi phục display:block,width:100%,
min-width:0,overflow:visible; chiều cao220px desktop/240px mobile giữ nguyên.
ResizeObserver/PiCharts hiện có tự tính lại viewBox/axes theo chiều rộng thật;
không thay dữ liệu, số điểm, tooltip hoặc polling. Hai ghi chú bên dưới rút gọn,
giải thích retention/checkpoint/mất điện vẫn có trong Trợ giúp Lưu trữ.

Node chart geometry/null/gaps/tooltips và polling đã qua. HTTP kiểm tra9trang/
14assets200, CSS trên release thực có width100%/displayblock;6dịch vụ active.
Chưa có kiểm tra hình ảnh mới do giới hạn công cụ trình duyệt đã nêu trên.
Release/snapshot4.0.2: `20261024T152212-198621`.

## 4.0.3 — Trạng thái phiên Camera trong thư viện

Thư viện trước đây đọc manifest lúc mới tạo phiên nên số ảnh hiện0, trong khi
bộ đếm trực tiếp đã tăng. Nhãn “Đang ghi / bị gián đoạn” cũng gộp hai trạng thái.
Agent nay ghép số liệu RAM của đúng ID và thư mục hiện hành vào kết quả list:
Đang ghi, Đang ghép, Bị gián đoạn, Đã ghép hoặc Chưa ghép. Manifest recording
không có job tương ứng được xem là gián đoạn, số ảnh chưa biết để null; không
giả định bằng0 và không quét toàn bộ ảnh ở mỗi lượt polling. Xem ảnh vẫn đọc
danh sách file thật khi người dùng mở gallery.

Status chỉ thêm tóm tắt render_session với trường công khai và đích lưu;
không gửi đường dẫn thư mục nội bộ, target hay PositionGate. Bộ đếm thư viện
dùng cùng status/heartbeat hiện có, nút ghép ẩn trong phiên đang ghi/ghép.
Sửa thêm so sánh last_result undefined/chuỗi rỗng vốn gây gọi list lại ở mỗi
status khi chưa có kết quả. Không thêm timer, ghi manifest định kỳ hay thay
đổi cơ chế chụp/ghép/giữ camera.

169 Python tests và Node camera lifecycle/gallery/state, interface/feedback,
charts/polling/Nonstop qua. Test mới xác minh list dùng counter RAM mà không
đổi byte/mtime manifest, phân biệt gián đoạn sau restart, không trộn thư mục
cùng ID, chuyển ghi→ghép→kết quả và cập nhật counter không gọi thêm list.
Đã được cài cùng4.0.4 sau khi người dùng cho phép kết thúc đúng phiên0ảnh;
release/snapshot20261024T171747-218231. Chi tiết trong V404_CAMERA_POSITION.md.
