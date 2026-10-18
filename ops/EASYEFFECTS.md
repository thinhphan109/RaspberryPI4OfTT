# EasyEffects trên Pi — 17/10/2026

## Preset nghe nhạc đã áp dụng

`Pi-Music-Gentle`: preamp −5 dB; low shelf 100 Hz +3 dB; bell 300 Hz −1 dB;
bell 2,5 kHz +1,5 dB; high shelf 8 kHz +0,5 dB. Hai kênh giống nhau, limiter
−1 dB không gain boost. Đây là điểm khởi đầu nhẹ, chưa hiệu chỉnh theo mẫu loa.
Chọn trong Output Presets để nạp lại; `Pi-Before-Music-20261017` khôi phục cấu hình
trước lần chỉnh. Có thêm bản dconf timestamp trong `~/.local/state/pi-audio/`.
Mức nghe có thể nhỏ hơn vì chừa headroom; không tự thay đổi volume phần cứng.

Đã cài EasyEffects 7.2.3 từ kho Debian 13 ARM64, cùng plugin LSP, MDA và Zam.
Pi được xác minh bằng SSH tại 192.168.1.30 trong lần cài này.

Mở **Easy Effects** từ menu ứng dụng trên desktop Pi. Ứng dụng chạy nền sau khi
đóng cửa sổ; tự khởi động khi tài khoản `thinh` đăng nhập desktop, không phải một
dịch vụ xử lý âm thanh trước khi đăng nhập.

Âm thanh ứng dụng PipeWire/PulseAudio được xử lý tự động. Đã xác nhận Chromium
đang đi vào Easy Effects Sink. Giữ thiết bị phần cứng làm đầu ra mặc định;
không đặt Easy Effects Sink làm mặc định. Ứng dụng xuất ALSA trực tiếp có thể
bỏ qua xử lý.

Cấu hình ban đầu: Equalizer phẳng → Limiter, threshold −1 dB, gain-boost tắt.
Không tự tăng bass hoặc âm lượng. Trong tab Output/Effects, chỉnh Equalizer
theo loa thực tế. Dùng nút Bypass để so sánh âm gốc; tránh đẩy nhiều dải EQ lên
cùng lúc gây quá mức tín hiệu. Chưa kiểm tra chất lượng bằng nghe thực tế.

Autostart: `~/.config/autostart/pi-easyeffects.desktop`.
Bản sao cấu hình trước thiết lập: `~/.local/state/pi-audio/easyeffects-before.dconf`.
Tiến trình hiện tại được khởi động bằng transient user unit `pi-easyeffects`.
Để dừng ngay: `easyeffects --quit`. Để không tự chạy ở lần đăng nhập sau, bỏ
file autostart trên; giữ gói cài và cấu hình nếu còn muốn sử dụng thủ công.

APT đã sửa gói fonts-noto-extra bị half-installed và hoàn tất 140 gói còn dang
dở từ trước, chủ yếu LibreOffice/Java/font. Không chạy autoremove hoặc xoá gói.
Sau cài, `dpkg --audit` không báo lỗi; AdGuard, Dashboard, Cloudflare còn active.

EasyEffects là ứng dụng desktop, không cung cấp giao diện chỉnh qua web tích hợp.
Việc mở GUI từ SSH được gửi tới phiên desktop đang hoạt động trên Pi.
