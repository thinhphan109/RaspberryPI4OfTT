# Media r5 — ghim nội dung, xác nhận lệnh và bảo vệ Bluetooth

Đã cài ngày28/10/2026 trên OS SSD. Bản cuối là gói r5e:

- Media: `v1-df37732000a8d48c`.
- Dashboard: `v1-b3929f65aeb1ab91`.
- Bộ cài root-owned: `/opt/pi-control-bootstrap-20261028-r5e`.
- Archive SHA256: `d9df919261f7ccd9f30fd88fbb4905c1b4e97da492f6ecc50499573e393a5760`.
- Manifest SHA256: `fed5ba7972033c80c75b8abe13da591950445999cde52b0b58d0229c2dbb657d`.

Sáu module còn lại giữ release trước. Chromium, Audio và Camera giữ nguyên
PID3469/1402/1375; chỉ agent Media và Dashboard được cập nhật. Không nâng gói
apt, thay Wi-Fi, thông tin đăng nhập hoặc profile tài khoản. Các bản r5b/r5c/r5d
trung gian có log riêng; không dùng checksum của chúng cho bản cuối.

## Sử dụng

Tải lại trang Media. Chọn YouTube hoặc Spotify, dán link, đặt tên rồi bấm
**Ghim link**. Bấm tên mục đã ghim để bật Media nếu đang nghỉ, chuyển nguồn và
phát. Có thể bỏ từng mục bằng nút× có nhãn trợ năng. Danh sách tối đa24 mục,
không đồng bộ với mục yêu thích trong tài khoản Spotify/YouTube.

YouTube nhận video hoặc playlist. Link watch có list giữ ngữ cảnh playlist;
link playlist mở trang rồi tìm video đầu trong đúng playlist đã chọn. Giữ kiểm
tra origin/HTTPS/video/list và danh sách không thích. Đề xuất và giới hạn của
nền tảng vẫn áp dụng; playlist riêng tư/không truy cập được cần xử lý trên Pi.
Spotify giữ URL bài/album/playlist/nghệ sĩ/podcast theo validator hiện có.

Thông báo điều khiển có3 trạng thái: đang kiểm tra, đã xác nhận, chưa xác nhận.
Gửi click thành công không tự thành báo phát/dừng thành công. Thời gian chờ xác
nhận là12giây; mở nguồn/nội dung/bật browser có tối đa45giây. Hết hạn không tự
gửi lặp thao tác. Trạng thái lệnh gần nhất dùng chung giữa các client quản trị.
GET cũ trong browser không được ghi đè kết quả của thao tác mới.

Spotify ưu tiên thời gian trên thanh tiến độ của Web Player. Khi xuất hiện một
audio element ngắn không khớp thời lượng bài, không dùng nó để hiển thị thời
lượng, tua hoặc chỉnh âm lượng bài. Điều khiển không xác minh được sẽ bị khóa;
không giả lập số0 thành trạng thái đã biết. Metadata/player đang phát không tự
chứng minh loa phát ra tiếng. Khi chưa có tín hiệu phù hợp, UI nói rõ chưa xác
minh âm thanh trên Pi.

## Bảo vệ Bluetooth

Mặc định bật **Tạm dừng khi mất loa Bluetooth**, có thể tắt rõ ràng bằng checkbox.
Chỉ theo dõi loa Bluetooth đang làm đầu ra mặc định. Không dừng nhạc khi một
thiết bị Bluetooth không được dùng mất kết nối, hoặc khi chủ động đổi sang đầu
ra khác trong lúc loa cũ còn hiện diện.

Khi loa đang dùng biến mất, hoặc không đọc được Audio trong2lượt liên tiếp sau
khi đã theo dõi loa, Media giữ trạng thái dừng: tắt tiếng/pause phần tử media,
hủy wake/pending-play, chặn Nonstop và tự tiếp tục. Hook cũng bảo vệ khi chuyển
trang trong cửa sổ Media riêng. Kết nối loa lại không tự phát. Chọn đầu ra rồi
bấm Phát, phát mục ghim hoặc chủ động Bật Media để bỏ trạng thái giữ sau khi
đã xác minh đầu ra mới.

Spotify có thể dùng audio tách khỏi DOM. Nếu không có phần tử để tắt tiếng an
toàn, guard cho **riêng browser Media nghỉ** thay vì chỉ báo đã tắt tiếng.
Giữ trạng thái qua restart agent bằng file0600 trong `/run/user/1000`, không
ghi trạng thái này định kỳ xuống SSD. Bật lại cần đầu ra vừa được xác nhận.

Theo dõi chạy khoảng3giây/lượt, Audio cache5giây, IPC có timeout2giây. Có độ
trễ; đây không phải cơ chế ngăn mọi tiếng lọt ra ngay thời điểm loa ngắt. Chưa
thử rút/tắt loa thật trong lượt này. Không kiểm soát ứng dụng ngoài Media.

## Lưu trữ và kiểm tra

`/var/lib/pi-control/media/shortcuts.json` có schema1, giới hạn24 mục/128KiB;
ghi atomic0600 và fsync khi thêm/xóa/đổi tên rõ ràng. Cùng URL chuẩn hóa chỉ
cập nhật tên, lưu giống hệt không ghi lại. File lỗi không bị thay bằng danh sách
rỗng. Polling, receipts và theo dõi Bluetooth không thêm lịch sử ghi SSD.
Checkbox guard dùng config Media hiện có, chỉ lưu khi người dùng thay đổi.

- 264 kiểm thử Python ứng dụng trên ARM đạt, gồm dữ liệu lỗi/race/trạng thái
  xác nhận/khôi phục mute/guard/source và playlist. Fixture không dùng config live.
- Node chạy đúng scripts Spotify, feedback/nguồn Media, DOM an toàn cho tên ghim,
  CSRF, GET cũ, không tăng poller và mute/pause/restoration: đạt.
- Bộ91file/8module/10unit kiểm tra fake-root ARM đạt; AdGuard check-config đạt.
- Live API: thêm/đọc/xóa một mục ghim tạm qua HTTP auth+CSRF đạt, không để lại
  mục thử. POST thiếu CSRF bị từ chối403. HTML254ID duy nhất,16asset trả200.
- Cả8 module được đối chiếu checksum với bundle đang chạy: đạt.
- Spotify ban đầu chưa có luồng âm thanh thật mặc dù nút báo Pause. Đã mở lại
  đúng playlist đang chọn, quan sát Chromium có luồng PipeWire tới RealfitS1 và
  thử pause/resume: receipt confirmed, trả về trạng thái phát. Không nghe thử loa.
- Bộ kiểm tra không chủ động ngắt loa Bluetooth hoặc đổi nguồn đang nghe sang
  YouTube. Ghim playlist YouTube có test logic; phiên playlist YouTube thật,
  physical Bluetooth loss, reboot và iPhone vẫn chưa nghiệm thu.
- Preview desktop dùng HTML/assets/snapshot đọc từ production, phục vụ qua
  localhost chỉ đọc; không dùng preview này làm bằng chứng thao tác player thật.

Bằng chứng: `ops/reports/media-deploy-20261028-r5e.out`,
`ops/reports/media-verification-20261028-r5e.json`. Script triển khai cố định hash
`ops/deploy-media-r5.py` đã chạy; không chạy lại trên destination đã tồn tại.
Preview browser đã đóng, HTTP server localhost đã dừng. Bước dọn thư mục preview
và staging trong `/tmp` bị cơ chế duyệt tự động chặn với lý do chung “blocked by
policy”; không thử né chặn. Các tệp tạm vẫn được giữ, không ảnh hưởng service.

Rollback từng module bằng bộ cài modular; rollback source không xóa danh sách
ghim/config tài khoản. Khi bỏ toàn bộ tính năng guard, cần giải phóng hold qua
bản mới hoặc đóng browser Media trước; bản cũ không quản lý hook guard trong
browser đã chạy. Không dùng Deploy legacy trên SSD.
