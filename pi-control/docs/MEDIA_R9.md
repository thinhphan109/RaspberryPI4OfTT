# Media r9 — Nonstop YouTube và phục hồi Spotify khi quảng cáo đứng

Đã triển khai ngày29/10/2026. Dashboard `v1-1b04d36b4bd7567a`, Media
`v1-34d0a867e91529db`; kit `/opt/pi-control-bootstrap-20261029-media-r9a`.

## Kết quả kiểm tra

uBlock Origin Lite vẫn ENABLED, không có disable reason/runtime error, có quyền
`<all_urls>`, đủ6 ruleset mặc định. Version2026.1026.1812 khớp bản mới nhất
[upstream](https://github.com/uBlockOrigin/uBOL-home/releases/tag/2026.1026.1812)
ở thời điểm kiểm tra. Policy vẫn đặt Optimal, không đổi quyền hoặc chế độ lọc.
Không phải extension bị gỡ. Reload riêng uBOL qua giao diện quản lý extension
của Chromium rồi tải lại trang Media; browser không khởi động lại.

YouTube trong cửa sổ chính đã phát bình thường:35 mẫu trong khoảng70 giây,
readyState4, thời gian tiến triển, không notice/playability error, không có mẫu
`ad-showing`. Thử một tab YouTube nền trước đó chưa tải xong video nên không
được tính là kết quả đạt. Chưa xác minh một lượt quảng cáo thật bị chặn; không
kết luận mọi quảng cáo YouTube đều đã được loại.

Spotify sau khi mở lại nguồn đã phát và chuyển qua6 title trong484 giây,92 mẫu,
4 lần Next bằng nút chuẩn. Không gặp lại quảng cáo trong lượt thử, không có lỗi
request Media được bộ thu ghi nhận. Chưa tái hiện lỗi quảng cáo đứng của người
dùng; không quy nguyên nhân chắc chắn cho uBOL hoặc thay đổi r8.
Upstream có ghi nhận [lỗi Chromium MV3 tương tự](https://github.com/uBlockOrigin/uBOL-home/issues/293).
Không thêm rule redirect media, không bật SpotiAds vào profile chính.

## Thay đổi đã cài

- Nonstop YouTube thực tế đang OFF khi bắt đầu kiểm tra. Đã bật và lưu bằng API
  hiện có. Nút đổi tên rõ **Nonstop YouTube**, luôn hiển thị; khi chọn Spotify,
  nút khoá và ghi rõ cần chọn YouTube. Trạng thái lưu của YouTube vẫn được hiển
  thị khi đang ở Spotify; không làm Spotify tự phát vì nút này.
- Status xuất rõ provider và `youtube_nonstop`, không phụ thuộc UI tự suy đoán.
- `AdStallGuard` dùng nhịp đọc Media hiện có. Chỉ quảng cáo được nhận diện rõ,
  có position đã biết, đang phát nhưng position/title/duration không thay đổi
  ít nhất105 giây mới yêu cầu `Page.reload` ở trang Spotify hiện tại.
- Không ép next/seek/rate, không thay DRM/TLS, không đọc token/cookie/form. Không
  tự tải lại khi người dùng tạm dừng, Bluetooth hold, standby, hết hẹn giờ ngủ,
  đang đăng nhập, không kết nối hoặc chưa biết position.
- Tối đa2 lần trong cửa sổ1 giờ, cách nhau ít nhất10 phút; giữ lượt thử trước khi
  gọi reload để lỗi reload không gây lặp. Bộ đếm ở RAM, mất khi agent khởi động
  lại. Chuyển nguồn/standby/hold xoá thời gian đứng, không xoá bộ đếm giới hạn.
- Hiển thị thông báo khi đang phục hồi hoặc đã chạm giới hạn. Đây là bảo vệ
  khỏi kẹt vô hạn, không phải bằng chứng đã chặn được quảng cáo Spotify.

## Bằng chứng và khôi phục

304 kiểm thử Python trên Pi; tất cả kiểm tra JavaScript và5 tình huống Nonstop
qua kiểm tra. Bộ cài ARM100 file/10 unit, import lịch sử67/lần lặp0 đạt.
Source hash cả8 module khớp bundle,288 ID duy nhất/21 asset, auth/CSRF và5 health
route đạt. Chỉ Media và Dashboard cập nhật;6 metadata module khác giữ nguyên.
Media khởi động lại; Browser495348, Camera1375, Audio80307 giữ nguyên.

Nonstop thực tế: tua video hiện tại tới3 giây cuối và để kết thúc tự nhiên.
Không gửi lệnh Next; quan sát URL tự chuyển từ
`8V1gSu1QMCQ` sang `PufPWA2_uoQ` (TOFU PLAYLIST HIT TRACKS), video mới đang phát
và có tiến độ. Sau đó khôi phục video gốc và vị trí2541.867968 giây; Nonstop ON.
Không có kiểm chứng nghe bằng loa vật lý.

Archive SHA256:
`be43b66e6b0dc8e8357ca92e2aff9a9051355a89112cee597c09b3b06dec7a77`.
Manifest SHA256:
`3c6de2496109c553a1de36aa14263041a205b1d75a14666d66fe5386c21e8484`.
Wrapper `ops/deploy-media-r9.py` đã chạy; không chạy lại ở destination cũ.
Rollback bằng bộ cài modular cho2 module; không Deploy legacy trên OS SSD.

Artifact local bị Git bỏ qua: `ops/reports/media-ad-audit-20261029/`, gồm
`before.json`, `spotify-before.json`, `spotify-summary.json`,
`youtube-main-check.json`, `nonstop-live-check.json`, `health-r9.json`.
Bộ thu chỉ giữ metadata phát và lỗi request Media với host/prefix đường dẫn;
không lưu header, body hoặc query URL. Monitor và tab thử đã dừng/đóng.
