# Pi Control Mobile r1

Đã deploy ngày 29/10/2026. Dashboard tự dùng bố cục mobile trên màn hình nhỏ.

## Giao diện điện thoại

Mở cùng địa chỉ Dashboard trên điện thoại. Ở chiều rộng tối đa 760 px, giao
diện dùng bố cục mobile riêng. Khi đổi sang màn hình lớn, bố cục desktop được
khôi phục; không cần đổi URL hoặc đăng nhập vào một ứng dụng khác.

- Thanh điều hướng dưới cùng: Tổng quan, Media, Camera, Mạng và Thêm.
  Menu Thêm dẫn tới Âm thanh, Ứng dụng & DNS, Lưu trữ, Hoạt động và GPIO.
- Nút Loa nằm trên đầu trang, mở bộ chỉnh âm lượng đầu ra hiện có.
- Media ưu tiên phần đang phát trước ô tìm kiếm. Nút phát/dừng lớn hơn,
  tìm kiếm có kết quả dạng danh sách và thao tác Phát/Ghim ngay trên từng dòng.
- Tổng quan giữ bốn thẻ tài nguyên trong hai cột. Các bảng dài cuộn bên trong;
  phần tra cứu GPIO tiếp tục giữ sơ đồ chân đọc được thay vì thu nhỏ chữ.
- Form dùng chữ 16 px, nút chính có vùng chạm tối thiểu 44 px. Bố cục chừa
  khoảng cho thanh điều hướng và safe area của điện thoại. Thanh dưới ẩn khi
  phát hiện bàn phím ảo đang mở; trở lại khi bàn phím đóng.
- Mỗi màn hình nhớ vị trí cuộn trong RAM trong lần mở trang. Các khối chức
  năng tiếp tục hiển thị trực tiếp; ghi chú dài nằm trong Trợ giúp hiện có.
- Menu hỗ trợ đóng bằng nút, Escape, chọn mục hoặc chạm ngoài. Đổi kích thước
  sang desktop cũng đóng menu và khôi phục vị trí DOM của các điều khiển.

## Cấu trúc

`templates/mobile.html`, `static/mobile.css`, `static/mobile.js` tách phần trình
bày điện thoại khỏi lớp bố cục desktop. Nội dung và điều khiển chỉ có một bản:
không tạo player, form hoặc ID trùng. JavaScript mobile chỉ sắp xếp DOM và điều
hướng; mọi lệnh thiết bị, CSRF, API và lịch đọc dữ liệu do controller hiện có
xử lý. Không thêm timer, tác vụ đọc API, package hoặc service cho mobile.

Stylesheet mobile chỉ áp dụng theo viewport; font Noto Sans/JetBrains Mono và
bảng màu đen hiện có tiếp tục được dùng. Asset có phiên bản theo release.

## Kiểm tra

- 284 kiểm thử Python ứng dụng qua trên Pi ARM.
- Test JavaScript mới kiểm tra chuyển mobile/desktop lặp lại, phục hồi đúng
  DOM, menu, nhớ cuộn, bàn phím và không có API/timer bổ sung. Các test polling,
  camera lifecycle, help và quick speaker hiện có đều qua.
- Bộ cài ARM trong fake root: 8 module, 98 file, 10 unit; cấu hình AdGuard qua,
  nhập 67 sự kiện lịch sử và nhập lại không trùng. Legacy Deploy DryRun qua.
- Bản xem trước chỉ đọc dùng template/asset thật và snapshot dữ liệu từ Pi:
  cả 9 màn hình ở 390 × 844 không tràn ngang; kiểm tra thêm 320 × 740 và
  430 × 932. Chuyển về 1366 × 900 khôi phục player/Loa về đúng vị trí desktop,
  không trùng ID. Escape đóng menu và trả focus về nút Thêm.
- Preview không gửi lệnh tới Pi. Chưa kiểm tra trên iPhone vật lý, bàn phím
  Safari hoặc safe area trên thiết bị thật.
- Production: chỉ Dashboard được cập nhật; bảy module còn lại giữ nguyên
  metadata, PID Media/browser/Camera lần lượt 230017/230590/1375 không đổi.
  Hash cả 8 module khớp manifest. HTML có 278 ID không trùng, 20 asset trả
  HTTP 200; kiểm tra auth, CSRF và 5 API đọc hiện có đều qua.
- Trên Dashboard production ở viewport 390 px: player nằm trước tìm kiếm,
  chỉ có một nút điều khiển phát, menu chuyển tới Lưu trữ rồi tự đóng và đánh
  dấu đúng tab Thêm. Popup Loa đọc được Realfit S1 ở 17%; không đổi âm lượng.

Ảnh local: `ops/reports/mobile-overview-preview.png`.
Ảnh production: `ops/reports/mobile-overview-live.png`.
Số đo local: `ops/reports/mobile-layout-checks.json`.

## Bundle và phạm vi deploy

Chỉ cài Dashboard `v1-ac307e1e21149e0c` từ
`/opt/pi-control-bootstrap-20261029-mobile-r1`.

Archive SHA-256:
`7d0127c10fbd0100c10832911af30c359d67d6111135e4a5bd8d21ca98e2f8c6`.

Manifest SHA-256:
`fb09d49ecb37812fabfe3a80e8ff38bb22eb1afd14fe359a87877e77d8d658e4`.

Entry point `ops/deploy-mobile.py` kiểm tra archive cố định, cài một module,
đợi HTTP login và đối chiếu metadata của bảy module còn lại. PID Media,
browser và Camera phải giữ nguyên. Lỗi kiểm tra sẽ rollback Dashboard.
Không chạy lại entry point nếu thư mục đích đã tồn tại; cần kiểm tra lần cài
trước thay vì ghi đè release.
