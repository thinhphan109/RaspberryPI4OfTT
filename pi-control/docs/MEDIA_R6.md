# Media r6 — Tìm nhạc và chỉnh loa nhanh

Đã deploy ngày 28/10/2026 trên OS SSD. Dashboard có ô tìm Spotify/YouTube,
nút Phát và Ghim cho từng kết quả. Nhạc vẫn phát trên loa của Pi.

## Cách dùng

1. Mở Media, bật Media nếu trình duyệt đang nghỉ.
2. Chọn nguồn tìm, nhập tên bài, nghệ sĩ hoặc playlist rồi bấm Tìm nhạc.
3. Bấm Phát để mở trên Pi; Ghim lưu vào danh sách thường nghe.
4. Nút Loa ở góc dưới bên phải mở âm lượng hệ thống của đầu ra đang dùng.
   Âm lượng này khác thanh âm lượng trong player. Chọn loa dẫn tới mục Âm thanh.
5. Với YouTube, chọn ưu tiên 240p để nghe nền, 360p để xem nhẹ hoặc Tự động.
   Dòng trạng thái hiển thị chiều cao video thực tế khi đọc được.

## Cơ chế và giới hạn

- Tìm kiếm đọc các thẻ kết quả hiển thị từ một tab tạm trong profile Media.
  Không đọc cookie, token, mật khẩu hoặc biểu mẫu đăng nhập; không dùng API key.
  Tab tạm chặn tự phát, ảnh và font; đóng sau khi đọc hoặc hết thời gian.
- Một tác vụ tìm tại một thời điểm, tối đa 12 kết quả; cache 8 từ khóa trong
  RAM trong 5 phút. Không tìm tự động khi gõ, không ghi lịch sử tìm xuống SSD.
- Tab tìm được loại khỏi bộ chọn player. Ledger tab tạm nằm trong thư mục
  runtime riêng để thu hồi sau khi agent khởi động lại. Giao diện Spotify/
  YouTube thay đổi có thể làm bộ đọc kết quả cần cập nhật; link trực tiếp vẫn có.
- Đây là giao diện điều khiển riêng, không phải bản sao đầy đủ của Spotify.
  Đăng nhập tiếp tục thực hiện trực tiếp trong cửa sổ Media trên Pi.
- Khi chọn nội dung khác nguồn, chỉ điều hướng một lần tới nội dung mới.
  Trình duyệt mở từ trang trắng; luồng chờ sẵn sàng kiểm tra mỗi 200 ms khi mở,
  thay vì chỉ phụ thuộc vòng kiểm tra 3 giây. Không mở browser do GET/status.
- YouTube dùng khả năng của player trên website để ưu tiên chất lượng.
  Không coi lời gọi API là bằng chứng đã giảm độ phân giải: đối chiếu videoHeight.
  YouTube vẫn có thể tự điều chỉnh; tính năng không biến video thành audio-only.
- Popup Loa chỉ đọc khi đang mở và trang hiện; ngừng đọc khi đóng/ẩn. Thanh kéo
  chỉ gửi khi chốt thay đổi. Agent kiểm tra lại ID, tên và đầu ra mặc định trước
  lệnh wpctl, không tự đổi route hoặc nâng âm lượng quá 100%.

## Lưu trữ

Phân vùng và trạng thái dịch vụ lên trước, tiếp theo là bản deploy. Quản lý
dịch vụ ở cuối, chia hai cột trên desktop và một cột trên điện thoại. Giữ nguyên
form, CSRF và các hộp Trợ giúp; không thêm mục phải mở rộng mới xem được.

## Đã kiểm tra

- 274 kiểm thử ứng dụng qua ở lượt cuối; 10 kiểm thử tập trung qua sau sửa
  chờ renderer, gồm trường hợp timeout rồi phục hồi, đóng tab và đầu ra đổi tên.
  Kiểm tra JavaScript hiện có và kiểm tra mới cho popup/tìm kiếm đều qua.
- Bộ cài ARM: 8 module, 95 file, 10 unit; kiểm tra cấu hình AdGuard qua trong
  fake root; không cài lên host trong bước thử này.
- Production: tìm từ khóa thử trả 12 kết quả mỗi nguồn; lần đầu Spotify khoảng
  15,6 giây, YouTube 12,2 giây. Cache cùng từ khóa đã kiểm tra. Đây chưa phải tốc
  độ như ứng dụng native; thời gian có thể thay đổi theo mạng và từ khóa.
- Cùng playlist Spotify đã chọn phát lại thành công sau khoảng 15,9 giây và
  xuất hiện luồng âm thanh Chromium chạy trong PipeWire. Chưa nghe trực tiếp
  âm thanh từ loa hoặc đo chất lượng âm thanh.
- Video YouTube ở tab thử tắt tiếng chuyển từ 480p xuống 240p thực tế.
  Đã đóng đúng tab thử. Không đo mức giảm CPU/watt hoặc thời gian cold start
  toàn phần của browser đang sử dụng.
- API popup đọc đúng loa, ghi lại cùng mức âm lượng trong khoảng 300 ms;
  tên đầu ra cũ bị từ chối. Trang có 272 ID không trùng, 18 asset trả HTTP 200.
- Bản xem giao diện dùng snapshot chỉ đọc kiểm tra desktop và 390 px: không
  tràn ngang; service Help hai cột/một cột. Chưa thử iPhone vật lý.
- Chỉ Audio, Media và Dashboard được cập nhật. Browser và Camera giữ nguyên PID;
  hash toàn bộ 8 module đang chạy khớp manifest gốc của từng bản đã cài.

## Bản đang cài

| Module | Release | Bundle |
|---|---|---|
| Audio | `v1-1ff508e4bf78ec48` | r6b |
| Dashboard | `v1-53d6e072f4cbfd19` | r6b |
| Media | `v1-718e27c828b7903e` | r6c |

Bundle r6b SHA-256: `db9f8745f1b7da84cc32decce3bb5e66a68ecab8f3d6818bafbc3885de955cd4`.
Bundle r6c SHA-256: `4f0a6508ac29f3116ffcd797700e5359293e2f7ed9965289edd66c0aea1013d2`.
Không khởi động lại browser chỉ để áp dụng unit mới trong khi đang sử dụng;
tham số trang trắng có hiệu lực ở lần mở browser tiếp theo.
