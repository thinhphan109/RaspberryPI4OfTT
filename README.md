# Pi Control — RaspberryPI4OfTT

Mã nguồn và công cụ vận hành hệ thống Raspberry Pi cá nhân: bảng điều khiển web, quản lý Wi-Fi, DNS, Media, âm thanh/Bluetooth và theo dõi phần cứng.

## Thành phần

- **Dashboard:** Flask/Gunicorn, đăng nhập, CSRF, giao diện sáng/tối, biểu đồ tài nguyên và GPIO chỉ đọc.
- **Mạng:** Wi-Fi fallback, chuyển Client/AP, tích hợp AdGuard Home và công cụ tự cập nhật DNS trên Windows.
- **Media:** điều khiển Chromium/YouTube, Nonstop, bỏ qua bài, chống lặp, hẹn giờ ngủ và cho Media nghỉ để giảm tài nguyên.
- **Âm thanh:** chọn đầu vào/đầu ra PipeWire, Bluetooth và phối hợp EasyEffects.
- **Theo dõi:** lịch sử tài nguyên trong RAM; thống kê lượng ghi thẻ SD được lưu riêng qua restart/reboot.
- **Vận hành:** triển khai theo release, kiểm tra sức khỏe và snapshot phục hồi trên Pi.

## Bắt đầu

Đọc [hướng dẫn vận hành](ops/README.md) trước khi kết nối hoặc triển khai. SSH cần khóa riêng trên máy quản trị; không lưu khóa hay mật khẩu vào repository.

Từ PowerShell tại thư mục dự án:

```powershell
.\ops\pi.ps1 -Action Check
.\ops\pi.ps1 -Action Deploy -DryRun
```

`Check` kiểm tra Pi qua SSH. `Deploy -DryRun` kiểm tra gói mã nguồn tại máy hiện tại. Đọc hướng dẫn trước khi chạy Deploy thật vì thao tác sẽ cập nhật dịch vụ trên Pi.

Mở `Pi-Control.cmd` để dùng bộ công cụ Windows. Xem [README ứng dụng](piwifi-manager/README.md), [tài liệu Dashboard](piwifi-manager/docs/DASHBOARD.md) và [bố cục GPIO](piwifi-manager/docs/V313_GPIO_LAYOUT.md) để biết thêm chi tiết.

## Phạm vi lưu trữ

Repository lưu mã nguồn, kiểm thử, tài liệu và tài nguyên giao diện. Mật khẩu, khóa SSH, cấu hình chạy thực tế, dữ liệu SQLite, log và snapshot phục hồi trên Pi không nằm trong bản sao này. Đây là bản lưu mã nguồn; muốn phục hồi toàn bộ hệ thống cần sao lưu dữ liệu và cấu hình trên Pi riêng.

Các thử nghiệm phần cứng còn chờ xác nhận được ghi trong tài liệu từng phiên bản. Giữ giấy phép đi kèm font và mã bên thứ ba trong `ops/vendor/`.
