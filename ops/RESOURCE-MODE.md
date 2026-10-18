# Cho Media nghỉ và bật lại

Dashboard 3.11 thêm nút **Cho Media nghỉ / Bật Media** tại Tổng quan và Media.

Cho nghỉ dừng riêng user service `pi-media-browser`, đóng Chromium chuyên phát
nhạc và các tiến trình con. Agent còn chạy để nhận lệnh bật lại; trạng thái nghỉ
được lưu khi người dùng bấm nút. Nonstop và hàng đợi không tự mở lại trình duyệt
trong trạng thái nghỉ, kể cả sau khi agent khởi động lại. Polling trạng thái nghỉ
không gọi CDP và không ghi cấu hình định kỳ.

Bật lại khởi động trình duyệt chuyên dụng. Khi Nonstop bật và có video hợp lệ
được lưu, cơ chế phục hồi hiện có có thể phát lại video đó từ đầu; không hứa giữ
vị trí tua. Khi Nonstop tắt hoặc đã hết hẹn giờ ngủ, chọn nội dung/Phát để nghe tiếp.
Queue vẫn trong RAM; triển khai hoặc khởi động lại agent làm mất queue như trước.

Các tab Chromium khác, EasyEffects, phiên desktop, Wi-Fi/fallback, AdGuard,
Dashboard và tunnel tiếp tục chạy. Đây là giảm tải Media, không phải ngủ toàn Pi
và không phải công tắc bật/tắt mọi dự án. Chưa đo điện năng bằng đồng hồ USB.

## Ngủ toàn Pi và đánh thức từ xa

Kiểm tra trực tiếp Pi 4 Model B Rev 1.5: `/sys/power/state` rỗng;
`/sys/power/disk` không tồn tại. Kernel đang chạy không cung cấp suspend/hibernate.

Nếu halt/poweroff, Linux và Dashboard dừng, không thể nhận nút đánh thức từ chính
Dashboard đang chạy trên Pi. Tài liệu Raspberry Pi mô tả đánh thức Pi 4 bằng
GPIO3/GLOBAL_EN tùy cấu hình EEPROM. Chức năng GPIO điều khiển từng bị hủy;
thay đổi này không chỉnh EEPROM hay bổ sung điều khiển GPIO.

Muốn đánh thức sau khi halt cần bộ điều khiển bên ngoài vẫn online hoặc phần
cứng quản lý nguồn. Không dùng rút/cấp nguồn đột ngột thay cho shutdown sạch.

Nguồn: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#WAKE_ON_GPIO

## Kiểm tra trước triển khai

39 kiểm thử Media (gồm 9 kiểm thử mới về nghỉ/bật, lưu trạng thái, chặn Nonstop,
phạm vi service cố định và lỗi lệnh) đã qua trên Python của Pi trong thư mục tạm.
JavaScript media.js qua kiểm tra cú pháp; gói Deploy DryRun hợp lệ.
Đã triển khai `20261018T165456-305538`; snapshot phục hồi cùng tên trong
`/var/lib/piwifi-deploy`. Đã thử nút nghỉ/bật qua Dashboard và private agent.
Khi nghỉ, browser inactive, agent/web/observer/guard/AdGuard/tunnel active;
HTTP login trả 200 và truy vấn DNS trực tiếp tới AdGuard thành công. Nonstop vẫn
bật nhưng không tự mở browser trong khoảng nghỉ khoảng một phút. Cờ nghỉ được
lưu; mtime cấu hình không đổi trong phép đo 10 giây khi nghỉ.

Khi bật lại, agent chủ động điều hướng về video đã lưu sau khi CDP sẵn sàng,
tránh nhầm video xem trước ở trang chủ YouTube là bài đang phát. Volume thật của
video được giữ trước khi nghỉ. Đã thử lại với đầu vào sẵn sàng: cùng video,
volume61%, has_video=true, paused=false sau khi bật. Media cuối cùng đang bật.

Đo cùng phiên: browser từ 11 tiến trình, CPU96,33% của một nhân trong 10 giây
xuống 0 tiến trình/0% khi nghỉ. RAM sẵn dùng từ 2174,7 lên 2978,4MiB (tăng
803,7MiB tại hai thời điểm đo; số này phụ thuộc tải/cache của toàn hệ thống).
Không chuyển các số CPU/RAM này thành mức điện năng tiết kiệm.

Tổng quan và Media đã kiểm tra ở390px và1366px, không tràn ngang; nút bấm đã
kiểm tra trực tiếp trên trang production. Chưa có thử nghiệm iPhone thật,
reboot hay nghỉ qua đêm. Không restart agent thật chỉ để kiểm tra latch vì
sẽ mất lịch sử trong RAM; việc nạp cờ sau restart được kiểm tra bằng unit test.

Mẫu trước triển khai: cgroup Chromium Media có 11 tiến trình, sử dụng CPU trung
bình 98,95% của một nhân trong 10 giây. Tổng RSS các tiến trình 1165,2MiB có tính
trùng bộ nhớ chia sẻ; không dùng số này như lượng RAM chắc chắn giải phóng hay
mức điện tiết kiệm. Chưa đo sau khi cho nghỉ.
