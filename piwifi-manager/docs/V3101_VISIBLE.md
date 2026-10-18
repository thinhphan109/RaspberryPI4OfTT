# Dashboard 3.10.1 — Hiển thị trực tiếp các chức năng

Người dùng yêu cầu giảm gom nhóm vào mục xổ xuống để không phải mở lại mỗi lần xem.
Quy tắc này thay thế cách thu gọn chức năng của bản 3.9.4.

- Chuyển 14 khối chức năng từ details/summary thành section có tiêu đề: cài đặt Media,
  hàng đợi, kiểm tra DNS, hồ sơ/quét/thêm Wi-Fi, chẩn đoán, lưu lượng, SSH,
  tiến trình, sự kiện, bản triển khai và dịch vụ.
- Giữ thu gọn phần hướng dẫn Media, giải thích âm thanh và chi tiết nguồn điện.
- Desktop chia cột với khoảng cách gọn; Media chuyển về một cột ở độ rộng <=900px.
  Sửa lỗi hai cột Media chồng lên nhau trên điện thoại.
- Giữ nền đen trung tính, màu đồ thị, ID, thuộc tính biểu mẫu, CSRF, API và nhịp polling.
  Không thay đổi chính sách phát nhạc hoặc cấu hình âm thanh/mạng.

Đã đối chiếu toàn bộ ID và thuộc tính form với bản trước khi sửa. Kiểm tra trực tiếp
8 tab ở độ rộng 390, 1366 và 1920px: 24 trường hợp không tràn ngang hoặc chồng card.
Media trên điện thoại là một cột, trên desktop là hai cột. Nội dung dài vẫn cuộn dọc;
không cam kết mọi dữ liệu luôn vừa một màn hình. Chưa kiểm tra bằng iPhone thật.

Bản triển khai: `20261018T130910-278807`.
Snapshot phục hồi trên Pi: `/var/lib/piwifi-deploy/20261018T130910-278807`.
Deploy xác nhận thành công; web, observer, guard timer, AdGuard và tunnel đang active.
