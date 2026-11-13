# Media r8 — điều khiển ứng dụng trên Pi

Ngày triển khai: 29/10/2026. Chỉ cập nhật Media và Dashboard trên OS SSD.

## Dùng từ Dashboard

Mở **Media → Ứng dụng trên Pi → Quét ứng dụng** sau khi mở VLC hoặc app hỗ trợ
MPRIS trong cùng phiên desktop của Pi. Chọn app, dùng Phát/Tạm dừng, bài trước/sau,
tua ±10 giây hoặc âm lượng. Nút không được app hỗ trợ sẽ bị khoá.

Khối này điều khiển app đang mở; không cài hoặc tự khởi động app. Spotify Free
hiện vẫn phát bằng Web Player. Không có Spotify Desktop ARM64 được cài trong bản này.

Âm lượng ứng dụng khác với nút **Loa**, vốn điều chỉnh đầu ra hệ thống. Hẹn giờ ngủ,
giới hạn âm lượng, Nonstop và bảo vệ Bluetooth hiện có chỉ áp dụng cho Web Player;
không tự áp dụng chúng lên VLC hoặc app khác.

## Thiết kế và giới hạn

- Dùng `busctl` có sẵn, không thêm playerctl/daemon/package. Danh sách app và trạng
  thái chỉ giữ trong RAM. Không quét lúc mở trang; chỉ quét khi bấm nút.
- Sau khi chọn app, đọc trạng thái cùng nhịp cập nhật Media đang có, chỉ khi mục
  Media đang hiển thị. Không thêm timer; không ghi cấu hình hoặc lịch sử mỗi lần đọc.
- Chỉ nhận các lệnh MPRIS cố định. Chromium và các trình duyệt phổ biến được loại
  khỏi danh sách này để tránh hai bộ điều khiển cùng tác động Web Player.
- Mỗi lựa chọn gắn với unique D-Bus owner. App khởi động lại thì khoá điều khiển và
  yêu cầu quét lại; lệnh không tự chuyển sang tiến trình mới dùng lại tên cũ.
- Alias cùng PID gộp thành một app. Gửi lệnh tới unique owner và đọc lại trạng thái;
  gửi thành công nhưng chưa thấy thay đổi sẽ báo chưa xác nhận.
- D-Bus không giữ browser policy lock; timeout và số ứng dụng được giới hạn.
  Native API vẫn dùng phiên đăng nhập Dashboard, CSRF và socket Media riêng.

## Bằng chứng triển khai

- Dashboard `v1-877171f1cc8edf45`; Media `v1-e23ae2ab286dd171`.
- Kit root-owned `/opt/pi-control-bootstrap-20261029-media-r8a`.
- Archive SHA256 `1bd19771e3a7e4e044b8d4ca82b44018e78a750b62c1ccb1c7e75ec7bb3abeb9`;
  manifest SHA256 `e769758e10e93f9c1079807c3d7124492e865aab6f623194316d5b5dfb5b3baf`.
- 298 kiểm thử Python trên Pi; toàn bộ kiểm tra JavaScript, DryRun đóng gói và
  bộ cài ARM 100 file/10 unit qua kiểm tra. Import lịch sử 67 sự kiện, lần lặp 0.
- Thử VLC thật bằng WAV im lặng với `--aout=dummy`: phát/dừng/tua/âm lượng qua
  D-Bus; API Dashboard thật xác nhận phát/dừng/âm lượng, từ chối owner cũ.
  Không có kiểm chứng nghe bằng loa thật. Unit VLC thử đã được dừng.
- HTML có 288 ID duy nhất, 21 asset trả 200; auth/CSRF và 5 health route qua kiểm
  tra; hash của cả 8 module khớp bundle đang cài. Sáu module khác giữ nguyên.
- Media agent khởi động lại theo deploy; browser PID230590, Camera1375 và Audio80307
  giữ nguyên. YouTube vẫn phát và tiến sang bài tiếp theo qua Nonstop.
- Preview bằng template/asset thật, dữ liệu VLC giả để xem giao diện: desktop1280
  và mobile390 không tràn ngang. Đây không phải kiểm chứng trên iPhone vật lý.

Khôi phục source bằng rollback module `media` và `dashboard` trong bộ cài modular.
Không dùng Deploy legacy khi đang boot SSD. Không đổi dữ liệu tài khoản/browser.

## SpotiAds: thử riêng trước khi quyết định

Thử [SpotiAds](https://github.com/tomer8007/spotify-web-ads-remover) MV3 v1.2.5,
commit `fd6b71475ddb3f89607902c174652fd14d226055` trong profile riêng. Không đưa
extension này vào profile Media chính trong bản r8.

`ops/spotify-trial.py` xác minh archive cố định, tạo profile0700, tắt lưu mật khẩu,
debug chỉ localhost18773 và unit transient riêng. Không sao chép cookie, không đọc
form đăng nhập, token/header/mật khẩu. Người dùng đăng nhập trực tiếp vào cửa sổ thử.
Status chỉ xuất metadata phát và cờ/counter công khai của extension.

Kernel Pi thiếu memory cgroup controller: `MemoryMax` không có hiệu lực thực tế.
Watchdog riêng đo PSS mỗi5 giây, dừng riêng trial khi vượt750MiB, RAM khả dụng dưới
512MiB hoặc hết2 giờ. CPUQuota150% nghĩa là tối đa1,5 core. Lượt đầu đã tự dừng tại
759,5MiB PSS; không kết luận nguyên nhân tăng RAM là do extension. Lượt warm sau
đã nhận bài và tiến độ, cả fetch/WebSocket hook đều có quan sát. Kiểm tra Chromium
extensions-internals xác nhận SpotiAds ENABLED; trial không nạp uBOL. DNS và
đường mạng hiện có của Pi được giữ nguyên; đây không phải thử nghiệm mạng tách biệt.

Âm thanh riêng trial được mute để không trộn với YouTube. Mute này phục vụ thử
nghiệm, không phải bằng chứng chặn quảng cáo. Chỉ counter tăng cùng lượt chuyển
quảng cáo và tiếp tục phát ổn định mới đủ căn cứ đánh giá chức năng chặn.

Kết quả cuối: 73 mẫu trong773 giây (72 mẫu đọc được), metadata chuyển qua5 bài;
fetch và WebSocket hook đều có quan sát. Không có mẫu nhận diện quảng cáo và
counter loại quảng cáo cao nhất vẫn0. PSS cao nhất trong các mẫu621,2MiB. Watchdog
dừng lượt warm khi RAM khả dụng toàn Pi còn459,9MiB, lúc đó trial PSS591,1MiB.
Không đủ bằng chứng quy mức thiếu RAM cho extension; hai browser cùng chạy gây
thêm tải. Không coi việc chưa gặp quảng cáo là bằng chứng chặn thành công.

**Quyết định:** giữ SpotiAds ngoài profile chính. Cả browser trial và watcher đã
dừng; profile đăng nhập riêng được giữ kín để thử lại sau, không tự chạy khi boot.
Không có SpotX/Spicetify/spotify-adblock/Wine/Box64/Soloist được cài. Media chính
giữ bộ lọc/chế độ mute quảng cáo đang có, không được mô tả là đã chặn Spotify100%.

Bằng chứng local: `ops/reports/spotiads-trial-20261029/spotiads-final-report.json`,
hai file observation, `final-health.json`, ảnh `native-desktop.png` và
`native-mobile.png`. Các artifact này được Git bỏ qua; runbook giữ kết luận và hash.
