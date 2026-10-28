# Media r7 — Sửa tìm kiếm và mở link nhạc

Đã deploy ngày 29/10/2026 trên OS SSD. Đã kiểm tra tìm kiếm, link và phát thật
trong browser Media trên Pi; cần tải lại Dashboard để nhận giao diện mới.

## Thay đổi

- Spotify có lựa chọn Bài hát / Playlist. Chờ đúng trang kết quả tải xong,
  bỏ các liên kết ở footer và carousel đề xuất để tránh lấy nhầm playlist.
- Ô link tự nhận YouTube hoặc Spotify, không còn phụ thuộc nguồn đang chọn.
  Nhận link YouTube rút gọn, link Spotify có `intl-vi`, tham số chia sẻ và URI
  dạng `spotify:track:...`. Chỉ mở các nguồn HTTPS được cho phép.
- Lệnh phát trả phản hồi sớm; trạng thái đang mở được theo dõi riêng. Tìm kiếm
  lúc Media đang nghỉ mở browser yên lặng, không tự phát lại bài cũ.
- Sửa khởi động nguội khi Chromium mở `chrome://newtab/` thay cho `about:blank`.
  Agent chỉ nhận đúng hai trang khởi động này trong profile Media riêng.
- Spotify chuyển link bài sang album kèm `highlight`: giữ lại mã bài, đối chiếu
  tên và ảnh bìa với metadata oEmbed công khai trước khi xác nhận phát đúng bài.
  Chọn đúng hàng bài hát khi album có nhiều bài, không bấm phát tuỳ ý bài đầu.
  Đối chiếu phần định danh ảnh bìa, bỏ phần mã kích thước 64/300/640 px.
- Khi Spotify báo playlist riêng tư, đã xoá hoặc không khả dụng, Dashboard
  hiển thị lỗi cụ thể thay vì coi nút Play là bằng chứng đã phát thành công.
- Sửa lưu âm lượng khi Spotify không cung cấp giá trị: không ghi giá trị 0
  thay thế thành âm lượng thật. Giữ link ngữ cảnh playlist khi cho Media nghỉ.
- Sau lỗi mạng khi tìm kiếm, nút Tìm nhạc hoạt động lại để thử lần nữa.

## Cách dùng

1. Trong Media, chọn nguồn tìm; với Spotify chọn Bài hát hoặc Playlist.
2. Nhập từ khoá và bấm Tìm nhạc. Bấm Phát ở kết quả mong muốn.
3. Hoặc dán link vào ô Link YouTube / Spotify rồi bấm Phát.
4. Chờ dòng đang mở chuyển thành trạng thái phát. Nếu Spotify báo nội dung
   không khả dụng, lấy một link công khai khác hoặc kiểm tra trên Spotify.

## Giới hạn và dữ liệu

Tìm kiếm dùng một tab tạm có giới hạn, tối đa 12 kết quả; cache 8 truy vấn trong
RAM trong 5 phút, gồm nguồn và loại kết quả. Không tự tìm khi gõ hoặc lưu lịch
sử xuống SSD. Tab tạm được đóng sau khi hoàn thành hoặc hết thời gian.

oEmbed chỉ lấy tên và ảnh bìa công khai khi chủ động phát một bài Spotify;
timeout 3 giây, giới hạn phản hồi 64 KiB, cache RAM tối đa 24 bài trong 10 phút.
Không chạy HTML trả về và không dùng OAuth, mật khẩu, cookie hay token tài khoản.
GET trạng thái chỉ đọc cache, không gọi oEmbed. Tham khảo
[Spotify oEmbed](https://developer.spotify.com/documentation/embeds/reference/oembed).

Nếu Spotify không trả metadata hoặc thay đổi giao diện, hệ thống có thể chưa
xác nhận được bài đã chọn. Tài khoản Free còn chịu giới hạn phát của Spotify;
thay đổi này không bảo đảm mọi bài hoặc playlist đều phát được.

## Kiểm tra trước deploy

- 284 kiểm thử Python ứng dụng qua trên Pi ARM.
- Kiểm tra JavaScript hiện có và bộ test DOM mới qua: trang đang tải, footer,
  kết quả đúng loại, widget Spotify v2, chuyển hướng album và chọn hàng bài.
- Bộ cài ARM trong fake root: 8 module, 95 file, 10 unit; cấu hình AdGuard qua,
  nhập 67 sự kiện lịch sử và nhập lại không trùng. Không cài host ở bước này.

## Bundle cuối

| Module | Release |
|---|---|
| Media | `v1-d598f81408ff65be` |
| Dashboard | `v1-4a175a9792107c65` |

Bundle r7h SHA-256:
`f41ba57d6c2781200e58cb5528761d905b671f5232acbdc90dcc5e772011a5c3`.

Các bundle r7c/r7d/r7f/r7g là bản deploy trung gian. Chỉ cập nhật Media/Dashboard;
không thay đổi unit browser hoặc Camera. Browser được đóng/mở có chủ đích để
kiểm tra khởi động nguội; Camera giữ nguyên PID 1375.

## Kết quả trên Pi

Các kiểm tra phát sau đây yêu cầu đúng nguồn/link, tiến độ tăng liên tục và
luồng âm thanh Chromium đang chạy trong PipeWire. Không chỉ dựa vào nút Pause.
Chưa nghe trực tiếp qua loa, nên không coi đây là kiểm tra chất lượng âm thanh.

| Trường hợp | Kết quả quan sát |
|---|---|
| Tìm Spotify Bài hát / Playlist và YouTube | Mỗi loại 12 kết quả, không lấy footer |
| Tìm mới | Khoảng 16–30 giây trong các lượt kiểm tra; còn phụ thuộc mạng/renderer |
| Cache cùng nguồn/từ khoá/loại | Khoảng 0,03 giây |
| Phát kết quả YouTube | Xác nhận khoảng 8,8 giây |
| Phát kết quả Spotify: Billie Jean | Xác nhận khoảng 18,4 giây |
| Link YouTube `youtu.be` khi đang ở Spotify | Xác nhận khoảng 9 giây |
| Link Spotify `intl-vi/track?...` khi đang ở YouTube | Xác nhận khoảng 21,9 giây |
| Playlist Spotify công khai | Phát Past Lives (Instrumental), xác nhận khoảng 33,6 giây |
| Tìm mới từ chế độ nghỉ | 12 kết quả trong 17,2 giây, không có luồng âm thanh tự phát |
| URI Spotify sau tìm kiếm nguội | Xác nhận Billie Jean khoảng 20,1 giây |
| Link Spotify phát thẳng từ chế độ nghỉ | Xác nhận khoảng 25,2 giây |

Các ca phát khi browser đã mở được kiểm tra trên r7g. Lượt này phát hiện ca
khởi động nguội lỗi; r7h chỉ bổ sung nhận diện trang New tab và đã kiểm tra lại
cả hai đường mở nguội. Không mô tả toàn bộ một lượt matrix r7g là đã qua.
API nhận lệnh phát trả phản hồi trong khoảng 5–963 ms ở các ca nêu trên;
thời gian đó khác thời gian tải trang và bắt đầu phát.

Hash source của cả 8 module đang cài khớp manifest từng bản. Dashboard có 273
ID không trùng, 18 asset trả HTTP 200; CSRF thiếu bị từ chối, truy cập chưa đăng
nhập chuyển về login. Các API kiểm tra metrics/events/deployments/status/storage
trả HTTP 200. Không có system/user unit ở trạng thái failed trong lần kiểm tra.

Đã thao tác trên Dashboard thật: tìm Billie Jean, nhận 12 kết quả, bấm Phát
ở kết quả đầu, thấy đúng bài/link và tiến độ tăng; bấm Tạm dừng sau khi thử.
Ảnh kiểm tra: `ops/reports/media-r7-search-live.png` trong workspace local.
Chưa kiểm tra iPhone vật lý hoặc mọi bài trong thư viện Spotify.

Playlist Spotify cũ `1E63szG0tsDw5zxWzyItkc` báo không khả dụng trên trang thật.
Cần dùng link còn truy cập được; không thể sửa quyền riêng tư hoặc bài bị xoá
từ Dashboard. Đăng nhập tài khoản tiếp tục thực hiện trực tiếp trên Pi.
