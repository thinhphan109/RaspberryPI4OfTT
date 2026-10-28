# 4.2 — Spotify Web Player trên Pi

Người dùng chọn Spotify Free, yêu cầu đăng nhập tùy chọn và giảm quảng cáo.
SpotX được gửi là bản vá Spotify Desktop Windows. Không chạy script SpotX hoặc
giả lập ứng dụng x86 trên Pi ARM. Dùng Web Player chính thức trong profile Media
hiện có; không dùng Web Playback SDK/API phát nhạc vốn yêu cầu Premium.

Nguồn: [SpotX](https://github.com/SpotX-Official/SpotX),
[Spotify Web Player](https://support.spotify.com/us/article/web-player-help/),
[SDK yêu cầu Premium](https://developer.spotify.com/documentation/web-playback-sdk/howtos/web-app-player/).
Pi đã có Chromium arm64 và libwidevinecdm0 4.10.2662.3+1; sự có mặt của gói
không tự chứng minh phát DRM thành công. Cần đăng nhập/phát thật để xác nhận.

## Sử dụng

Media → Bật Media → Spotify. Đăng nhập trên Pi mở trang accounts.spotify.com;
nhập thông tin trực tiếp trên màn hình Pi hoặc qua công cụ remote desktop đang
có. Dashboard không có ô mật khẩu, không đọc form đăng nhập, cookie hoặc token.
Không bắt buộc đăng nhập để mở trang; nghe đầy đủ theo yêu cầu của Spotify.

Dán link open.spotify.com của bài hát, album, playlist, nghệ sĩ hoặc podcast,
bấm Phát ngay. Giữ domain/HTTPS/path allowlist, bỏ query chia sẻ, không nhận
link rút gọn hoặc URI tùy ý. Có nút phát/dừng, bài tiếp, tua khi player cho phép,
âm lượng, ảnh/tên/nghệ sĩ và trạng thái đăng nhập. Tự thử nút phát của trang đã
chọn trong45giây; không qua CAPTCHA/điều khoản hoặc lặp tải lại khi chưa đăng nhập.

Spotify quản lý hàng đợi/đề xuất và giới hạn Free. Nonstop/chống lặp/Không thích
YouTube được ẩn trong nguồn Spotify và không chạy trên nguồn này. Hẹn giờ ngủ,
giới hạn âm lượng và cho Media nghỉ dùng chung. Nguồn được lưu theo thao tác;
URL YouTube và queue RAM vẫn được giữ riêng. Không ghi tiến độ định kỳ.

## Giảm quảng cáo

uBlock Origin Lite hiện có vẫn lọc theo chính sách Chromium. Checkbox chỉ bật/
tắt phần tắt tiếng dự phòng khi trang có dấu hiệu quảng cáo rõ ràng. Không chỉ
dựa vào tên bài “Advertisement”; không tua ép, tải lại để vượt quảng cáo, tắt
DRM hoặc sửa chứng chỉ. Giữ trạng thái mute trước đó; khôi phục khi hết quảng
cáo, tắt tính năng hoặc đổi nguồn, kể cả audio element được thay mới. Hiệu quả
lọc Spotify thay đổi; chưa khẳng định chặn được toàn bộ quảng cáo.

## Kiến trúc và kiểm tra

spotify_player.py có URL validator, state allowlist và JavaScript cố định;
media_agent.py định tuyến theo nguồn trên private IPC hiện có. Chỉ nhận trạng
thái từ open.spotify.com. Nếu chuyển sang accounts.spotify.com, trả thông báo
đăng nhập mà không evaluate DOM. Không thêm cổng/service/OAuth credential.
Đóng nguồn trước khi chuyển, chỉ điều khiển cửa sổ Media riêng. Quá trình chọn
nguồn thất bại không báo đã đổi thành công. Source/module được thêm đầy đủ vào
installer, deploy allowlist và AST. Policy/cookie profile ngoài source rollback.

212 kiểm thử Python và Node kiểm tra đúng script quảng cáo, đổi audio element,
khôi phục mute, UI chuyển nguồn/capability/CSRF, không tăng poller, cùng các kiểm
tra camera/interface/feedback/charts/polling/Nonstop hiện có đã qua. Chưa có
đăng nhập Spotify, phát tài khoản Free hoặc quảng cáo thật; không gọi đây là
kiểm chứng phát nhạc end-to-end. Visual/mobile/iPhone vẫn chưa kiểm tra.

Đã triển khai release/snapshot `20261026T103747-20600`. Production HTTP/HTML:
9 trang/221 ID/14 assets, controls/source metadata và API nguồn không hợp lệ/
thiếu CSRF đều đạt qua ops/verify-spotify.py và verify-interface.py. Giữ nguồn
YouTube đang dùng; không chuyển bài để test. Sáu dịch vụ active, nhật ký gộp
không báo lỗi. uBOL cài bản2026.1021.1354. Người dùng được hướng dẫn đăng nhập
trực tiếp trên Pi và thử bài; phát Free/DRM/quảng cáo thực tế vẫn đang chờ.

Lượt kiểm tra cuối: người dùng đã chọn Spotify, agent nhận trang đăng nhập và
báo chờ hoàn tất trên Pi; không evaluate DOM của accounts.spotify.com. Chưa
quan sát phát nhạc thực. Lưu ý dừng player trước khi hoàn trả mute lúc đổi
nguồn để không phát ló tiếng quảng cáo.
