# Camera4.0.4 — Chẩn đoán phiên theo vị trí không chụp

Ngày25/10/2026, người dùng báo theo vị trí không còn hoạt động sau chọn lại
vùng mẫu. Kiểm tra chỉ đọc phiên20261024T170527-17d957e5: webcam720p hoạt động,
frame_sequence tăng, error rỗng, SSD còn45GiB, phiên position chưa có ảnh.
Phiên trước20261024T152849-b13d2283 đã ghép19ảnh thành công. Production vẫn4.0.2;
bản4.0.3 chưa cài vì người dùng muốn giữ recording.

Mẫu mới có threshold15%, settle0,2s. Quy tắc rời cần một trong hai sai lệch lớn
hơn1,5×threshold=22,5% trong0,4s, sau đó cả hai trở lại≤15% và ổn định0,2s.
100lượt status trong khoảng25s: đầu in0,9–11,6%, bàn0,6–10,8%,100lượt inside,
0lượt outside. Bởi vậy gate không armed; chưa chứng minh điều này cho toàn bộ
chu kỳ in dài hơn. ROI bàn chiếm58,8% khung hình, ảnh mẫu chứa vật thể và nền.
Cấu hình này làm khó phân biệt rời mẫu; không phải webcam/SSD bị ngắt.

## Thay đổi đã chuẩn bị

- PositionGate giữ phase và tối đa360mẫu RAM; diagnostics đọc cửa sổ30giây,
  báo threshold, departure_threshold, armed, recent_max và số mẫu.
- Không đổi điều kiện chụp, cooldown hay quyết định armed; không tự nới ngưỡng.
- Session note phân biệt chờ rời, đang xác nhận rời, chờ quay lại, chờ ổn định,
  cooldown và đã chụp. Status thêm tracking và cảnh báo ROI lớn hơn35%khung.
- UI hiện ngưỡng đang dùng và max sai lệch, giữ bản chỉnh chưa lưu, khóa chỉnh
  lúc recording/rendering. Cảnh báo gọn, chỉ hiện khi cần.
- Bao gồm bản sửa thư viện4.0.3 đang chờ; không thêm timer hoặc durable writes.

## Kiểm tra và giới hạn

173Python tests qua, gồm mô phỏng số đo thực không armed ở15% nhưng chu kỳ
rời/về được nhận ở6%, phase transitions, bounded samples và inspection không
đổi quyết định; status không đổi byte/mtime manifest. Node camera lifecycle,
gallery, counts, ngưỡngserver, bản chỉnh chưa lưu, tracking visibility; interface,
feedback, charts, polling và Nonstop qua. Validator tiếng Việt0lỗi/0cảnh báo.

Lần Deploy đầu bị chặn trước thay đổi: người dùng báo đã kết thúc nhưng agent
vẫn ghi0ảnh. Sau khi người dùng cho phép rõ “Kết thúc phiên 0 ảnh và cài bản sửa”,
đã kiểm tra đúng ID và0ảnh trước khi gửi stop. Phiên chốt incomplete0ảnh, không
có MP4 vì dưới2ảnh. Triển khai qua ops/pi.ps1 thành công với release/snapshot
`20261024T171747-218231` (giờ Việt Nam00:17ngày25/10),version4.0.4.

Sau khi idle, đã sao lưu nguyên cấu hình rồi đưa threshold15%về6%, giữ ảnh mẫu,
hai ROI và settle0,2s. Backup0600 thuộc userthinh:
`/home/thinh/.local/state/pi-camera/calibration-before-v404-20261024T171903Z.json`.
Chỉ thực hiện khi agent báo không ghi/ghép và threshold vẫn đúng15%; khởi động
lại riêng pi-camera để nạp. Source rollback không hoàn tác cấu hình runtime này.

Production authenticated HTTP:9trang,209IDkhông trùng,14assets200. Gallery cũ19ảnh
đọc JPEG đầu/cuối và download byte-identical; kiểm tra auth/header/index/storage
preference qua. Sáu dịch vụ web/observer/guard/AdGuard/camera/Media active.
Status xác nhận threshold6%,settle0,2s, không recording/rendering. Library đúng
incomplete0,ready19,incomplete1. Camera tự nghỉ; mô phỏng bằng hình trực tiếp
được bỏ qua vì không có frame khi idle, không bật camera hoặc ghi phiên mới.

Vùng bàn58,8% vẫn cần chọn lại khi đúng vị trí chụp. Mốc6%/0,2s là điểm bắt đầu
hiệu chỉnh, chưa bảo đảm chính xác mỗi lớp. Chưa có kiểm tra trực quan mới,
iPhone thật hoặc xác nhận chu kỳ in thật sau cấu hình mới; giới hạn công cụ
trình duyệt đã ghi ở V40_INTERFACE.md vẫn áp dụng. Người dùng cần tải lại trang
để nhậnJSmới và chọn mẫu/khởi động phiên khi sẵn sàng.
