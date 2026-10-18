# Dashboard 3.2.1 — áp dụng mẫu giao diện người dùng

Ngày 14/10/2026, dùng file mẫu mới nhất `8d37ff40-a692-456a-869f-80a53db1fafd/Pasted text.txt`, thay cho mẫu `9e006acf-cf69-4ab8-b9f8-e966df56afe9`.

- HTML/Jinja: templates/index.html. CSS của mẫu tách ra static/dashboard.css, ghép lên CSS nền để giữ nút/form/scan/disk/chart và các lớp do JS tạo.
- Dùng Noto Sans và JetBrains Mono bundled; không Google Fonts/CDN, không thêm Inter từ mẫu đầu. Đã dọn các asset/script thử của mẫu đầu.
- Giữ toàn bộ ID, data-tab, CSRF, endpoint và JS/backend bản3.2. Font tiếng Việt, theme và offline tiếp tục hoạt động.
- Mobile: sửa nav thành hàng cuộn ngang và ẩn footer theme lặp; không tràn ngang ở390px. Sửa specificity màu nhóm chân GPIO để các chấm nguồn/I2C/SPI/UART đúng nhóm.
- Chú thích lịch sử và rollback phản ánh RAM mất khi observer restart; DB cũ/profile vẫn được giữ.
- 41unittest Linux, kiểm thử Node timer lifecycle và packaging DryRun đạt. Preview desktop/light/dark/mobile390px, production qua tên miền, không thấy lỗi JS.
- Không lặp bài đo CPU10phút vì không đổi collector/polling/backend; số0,433% trong V32_RELEASE.md là phép đo bản3.2 trước thay giao diện, không phải phép đo mới.

Release: `/opt/piwifi-releases/20261014T055321-13416`.
Snapshot: `/var/lib/piwifi-deploy/20261014T055321-13416`.
Web, observer và guard được xác minh sau deploy. Lịch sử RAM bắt đầu lại theo chính sách3.2.
Ảnh production: docs/screenshots/v321-overview.png.
