# SpotX trên Raspberry Pi — đối chiếu ngày 28/10/2026

Khảo sát mở rộng ngày 29/10/2026: [các dự án Spotify cho Dashboard](SPOTIFY_PROJECT_SURVEY_20261029.md).

## Kết luận

SpotX không patch Spotify Web Player đang dùng trong Dashboard. Repo được gửi
là patcher cho Spotify Desktop trên Windows, yêu cầu Windows 7–11 và PowerShell
5.1 trở lên. Không cài bản này lên Debian ARM64 của Pi.
[SpotX chính thức](https://github.com/SpotX-Official/SpotX)

SpotX-Bash có bản Linux/macOS, nhưng nhánh Linux đặt kiến trúc x86_64 và sửa
binary cùng gói giao diện `Apps/xpui.spa` của Spotify Desktop. Nó cần client
Desktop phù hợp trước, không phải chỉ cài Bash là dùng được trên mọi CPU.
[SpotX-Bash](https://github.com/SpotX-Official/SpotX-Bash),
[mã nguồn](https://github.com/SpotX-Official/SpotX-Bash/blob/main/spotx.sh)

Kho APT chính thức của Spotify đang khai báo `Architectures: amd64 i386`,
không có ARM64. Pi hiện chạy aarch64. Đây là điểm chặn cho cách cài native.
[Metadata kho Spotify](https://repository.spotify.com/dists/stable/Release)

## Các hướng có thể chọn

| Hướng | Đánh giá cho hệ thống hiện tại |
|---|---|
| Chromium ARM64 + Web Player + bộ lọc trình duyệt | Phù hợp nhất để tiếp tục vận hành; dùng lại đăng nhập, Widevine và điều khiển hiện có. Việc chặn quảng cáo không được bảo đảm cho mọi lần phát. |
| SpotX trên máy Windows riêng | Đúng nền tảng của SpotX; âm thanh phải truyền từ Windows tới Pi/loa bằng một cơ chế riêng. Máy Windows phải chạy, không còn là giải pháp Pi độc lập. |
| Spotify Linux x86_64 qua lớp dịch CPU + SpotX-Bash | Chỉ là hướng thử nghiệm. Cần chứng minh tương thích client/DRM và đo RAM/CPU/độ trễ trên Pi 4; chưa cài, chưa kiểm thử, không coi là phương án tăng tốc. |

Ưu tiên giữ Web Player đang chạy và kiểm tra bộ lọc theo từng website. Không
thêm domain chặn rộng vào AdGuard để xử lý quảng cáo Spotify: việc chặn nhầm
endpoint cần cho phiên phát có thể làm player đứng. Checkbox hiện tại chỉ
tắt tiếng khi có tín hiệu quảng cáo rõ; nó không biến tài khoản Free thành
Premium và không chứng minh quảng cáo đã bị loại khỏi luồng.

Lần nghiên cứu này không chạy installer SpotX/SpotX-Bash, không cài Wine hoặc
lớp dịch CPU, không sửa DRM/TLS và không thay đổi bảo vệ đăng nhập.
