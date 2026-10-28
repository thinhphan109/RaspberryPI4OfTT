# Camera máy in Bambu Lab A1

Dashboard `#camera` dùng một FFmpeg reader cho webcam USB Generic `4a54:5233`.
Camera không thay thế camera tích hợp A1, không kết nối tài khoản Bambu và không
gửi G-code, lệnh chuyển động hoặc lệnh dừng máy in.

## Xem trực tiếp và chụp theo thời gian

1. Mở Camera · Máy in 3D; camera tự bật khi chế độ tự động đang bật. Vẫn có nút **Bật camera**.
2. Chọn **Theo thời gian**, chu kỳ 2–60 giây, chọn nơi lưu.
3. Bấm **Bắt đầu phiên**. Xem trực tiếp vẫn hoạt động trong lúc ghi.
4. Bấm **Kết thúc & ghép**. Khi MP4 sẵn sàng, bấm **Tải MP4**.

Preview 1280×720 tối đa 4 ảnh/giây, chỉ tải khi trang Camera đang hiện và browser
không bị ẩn. Một lần chỉ có một request ảnh đang chờ. Webcam cấp MJPEG 30 fps;
agent giữ ảnh RAM tối đa khoảng 10 fps và dùng lại cho preview/nhận vị trí.
Không có cổng camera public hoặc MJPEG stream dài chiếm gunicorn worker.
GET ảnh, video, trạng thái đều yêu cầu phiên dashboard; POST cần CSRF.

## Theo vị trí: thử nghiệm với Smooth Timelapse

1. Bật Smooth Timelapse và Timelapse khi gửi bản in từ Bambu Studio.
2. Gá webcam chắc chắn, quan sát vị trí bàn/đầu in trong chu kỳ chụp của A1.
3. Bấm **Giữ ảnh mẫu** lúc cả hai ở đúng vị trí mong muốn.
4. Chọn nút vùng đầu in rồi kéo một hình chữ nhật quanh chi tiết dễ nhận ra của
   đầu in. Chọn nút vùng bàn in rồi kéo quanh chi tiết của bàn; tránh vật thể đang
   lớn dần và phần nền không chuyển động. Hai vùng có màu xanh/cam riêng.
5. Bấm **Lưu vị trí chụp**, chọn **Theo vị trí**, bắt đầu phiên.

Có thể chọn vùng bằng bàn phím: Tab tới canvas, mũi tên di chuyển, Shift+mũi tên
đổi kích thước. Ảnh mẫu có hiệu lực 5 phút trước khi lưu. Mẫu đã lưu tồn tại qua
restart; thay góc camera/ánh sáng hoặc độ phân giải cần hiệu chỉnh lại.

Agent so sánh hai ảnh xám thu nhỏ với mẫu, yêu cầu rời vùng mẫu ít nhất 0,4 giây,
trở lại và ổn định (mặc định 0,2 giây), rồi chỉ lấy một ảnh cho lần trở lại đó.
Sai lệch mặc định 6%, có thể điều chỉnh 2–20%; ổn định 0,1–2 giây. Thời gian chờ
quá lớn có thể bỏ lỡ lúc A1 đậu đầu in. Ngưỡng quá rộng hoặc vùng ít chi tiết có
thể chọn sai. Đây là nhận diện ảnh đơn giản, **không bảo đảm một ảnh đúng mỗi lớp**.
Phải kiểm tra bằng bản in nhỏ thật và đối chiếu số ảnh/chất lượng.

Nếu phiên chạy nhưng số ảnh không tăng, kiểm tra ngưỡng và vùng chọn trước.
Ví dụ ngưỡng15% yêu cầu ít nhất một vùng vượt22,5% liên tục0,4giây để xác nhận
đã rời mẫu; nếu sai lệch chỉ0–12%, hệ thống luôn coi là đang ở mẫu và không chụp.
Tăng ngưỡng không đồng nghĩa nhận chuyển động tốt hơn. Chọn chi tiết nhỏ trên
đầu in và mép/góc bàn in; tránh vùng chứa phần lớn khung hình, vật thể đang in,
cuộn nhựa hoặc nền. Kết thúc phiên trước khi lưu mẫu mới, thử từ6%/0,2giây rồi
quan sát một chu kỳ rời–trở lại thực tế. Không tự đổi ngưỡng giữa phiên.

Bản4.0.4 đã chuẩn bị trạng thái chờ rời mẫu/chờ quay lại/chờ ổn định, thống kê
sai lệch cao nhất30giây trong RAM và cảnh báo vùng rộng hơn35% khung hình.
Đây là cảnh báo hỗ trợ hiệu chỉnh, không phải kiểm định độ chính xác vùng chọn.
Ô ngưỡng/ổn định đồng bộ giá trị đã lưu, giữ bản chỉnh chưa lưu khi polling và
khóa khi ghi/ghép. Không thêm polling hay ghi cấu hình định kỳ.

Chưa có liên kết MQTT/trạng thái A1, tự bắt đầu/kết thúc theo job, hay trigger
chụp chính xác từ firmware. Không dùng tín hiệu đổi lớp như bằng chứng đã đậu
đầu in. Không cài OctoPrint/Klipper hoặc sửa firmware máy in để làm chức năng này.

## RAM và SSD

- Chưa có SSD: vùng thử trong `/run/user/1000/pi-camera-trial`, chỉ RAM/tmpfs.
  Mỗi phiên tối đa 10 phút hoặc 64 MiB ảnh; tổng vùng thử giới hạn 128 MiB gồm
  chỗ dành ghép video. Không phù hợp lưu cả bản in dài; mất khi logout/reboot.
- SSD: sau khi được mount và có quyền ghi của user `thinh`, các phân vùng USB
  ext4/exFAT/NTFS/FAT32/XFS/Btrfs tại `/media/…` hoặc `/mnt/…` xuất hiện trong
  danh sách (cập nhật tối đa 15 giây). Chọn phân vùng mong muốn trước khi ghi.
  App tạo riêng thư mục `PiCamera`; không format hoặc đổi cấu trúc dữ liệu cũ.
- Từ 3.14.2, đổi mục **Lưu vào** sẽ nhớ UUID phân vùng trong
  `~/.local/state/pi-camera/storage.json` (chỉ ghi khi chủ động đổi lựa chọn).
  Mount ở đường dẫn khác vẫn nhận đúng ổ. Nếu SSD đã nhớ chưa kết nối, nút ghi
  bị khóa; không tự chọn RAM hoặc một ổ USB khác. Muốn thử RAM phải chọn rõ.
- SSD hiện tại: phân vùng NTFS `Metech3D`, UUID `01DD5FF0C7B1A200`, mount riêng
  `/mnt/pi-camera-ssd`; ảnh/video nằm trong `/mnt/pi-camera-ssd/PiCamera`.
  `/etc/fstab` dùng UUID, `ntfs3`, `nofail`, thời gian chờ thiết bị 5 giây,
  `noatime`, uid/gid1000. Mount khi boot không cần desktop; thiếu SSD không
  làm boot thất bại. Phân vùng FAT32 còn lại và dữ liệu có sẵn được giữ.
  Nếu gắn lại giữa phiên mà hệ thống chưa mount: `sudo mount /mnt/pi-camera-ssd`.
  Tháo ổ an toàn sau khi kết thúc ghi/ghép: `sudo umount /mnt/pi-camera-ssd`.
  Pi OS vẫn chạy trên thẻ SD; thay đổi này chỉ chuyển nơi lưu camera.
- Mỗi phiên SSD tối đa 24 giờ, 5 GiB ảnh hoặc 20.000 ảnh. Dừng trước khi còn dưới
  1 GiB trống. Không tự xóa các phiên cũ; xóa bằng nút **Xóa phiên** sau khi tải.
- Mount/device được kiểm tra trước khi ghi; mở file ảnh qua directory descriptor.
  SSD bị rút không chuyển sang thẻ SD. Giữ ảnh đã có để phục hồi sau khi gắn lại.
- MP4 H.264 30 fps, một thread mã hóa, tối đa 30 phút ghép; kiểm tra số frame
  đầu ra bằng ffprobe. Nếu thiếu frame/ghép lỗi, giữ ảnh gốc và báo chưa hoàn tất.
- Nếu dịch vụ/reboot cắt phiên SSD giữa chừng, chọn **Ghép ảnh gốc** để thử ghép
  lại từ chuỗi JPEG liên tục. Ảnh RAM không thể phục hồi sau reboot.

## Xem ảnh của phiên (3.14.3)

Trong **Video & ảnh gốc**, bấm **Xem ảnh** ở phiên cần xem. Khung ảnh có nút
Trước/Sau, phím ←/→, thanh chọn và ô **Đến ảnh** (nhập số rồi Enter). Số thứ tự
1…N là thứ tự ảnh thực sự còn trên ổ; tên JPEG gốc hiện riêng. Bấm **Tải ảnh
gốc** để tải đúng JPEG đang xem. Escape hoặc **Đóng** để trở lại Dashboard.

Chỉ tải một ảnh khi chọn, không tải trước toàn phiên, không có polling mới
trong thư viện. Mở lại khung để cập nhật ảnh mới nếu phiên vẫn đang ghi.
Mở khung ảnh tạm ngừng preview/heartbeat của tab này; phiên timelapse đang ghi
vẫn giữ camera. Đóng khung khôi phục xem trực tiếp theo lựa chọn tự động hiện có.

Ảnh trên RAM và SSD đều dùng được khi dữ liệu vẫn còn. Các GET danh sách/JPEG
yêu cầu đăng nhập, không tạo phiên ghi, không lưu thêm ảnh hoặc đổi nơi lưu.
Nếu SSD bị tháo hoặc ảnh bị xóa, báo lỗi thay vì chuyển nơi đọc/ghi sang SD.

## Tự bật/tắt theo người xem (3.14.1)

Mặc định bật **Tự bật khi xem, tự tắt khi không dùng**. Khi mở mục Camera trên
trang đang hiện, browser đăng ký một phiên xem riêng và gia hạn mỗi4giây.
Chuyển mục khác, ẩn browser, chuyển ứng dụng trên điện thoại hoặc đóng trang
sẽ gửi thông báo thôi xem. Không còn người xem và không ghi timelapse: sau
khoảng5giây camera đóng thiết bị thật và FFmpeg thoát, không chỉ ngừng hiển thị.

Nếu browser bị tắt đột ngột không gửi được thông báo, phiên tự hết hạn sau15giây;
cộng thời gian chờ và watchdog khoảng20–21giây để tắt. Hai thiết bị cùng xem:
một thiết bị thoát không tắt camera của thiết bị còn lại. Poll trạng thái, tải
video hoặc GET ảnh đơn lẻ không tạo/gia hạn phiên xem.

Timelapse đang ghi luôn giữ camera, kể cả không ai mở web. Nút Tắt camera bị
khóa khi đang ghi; phải Kết thúc & ghép trước. Sau khi phiên kết thúc, không
người xem thì camera tự nghỉ. Ghép video không cần giữ webcam.

Tắt thủ công khi đang xem sẽ được giữ, heartbeat không tự bật lại. Bấm Bật
camera để tiếp tục, hoặc rời hết các phiên xem rồi mở lại. Tắt checkbox tự động
để điều khiển hoàn toàn bằng nút bật/tắt, kể cả muốn camera chạy liên tục.
Chỉ lựa chọn checkbox được lưu `~/.local/state/pi-camera/power.json`; danh sách
người xem/heartbeat/thời gian chờ ở RAM, không ghi định kỳ lên SD.

## Runtime và khôi phục

`pi-camera.service` chạy user `thinh`, socket riêng `0600`
`/run/user/1000/pi-camera.sock`. CPUQuota=100% một core, MemoryMax=512M.
Giới hạn là trần tài nguyên, không phải mức tiêu thụ đo được. Agent mặc định
không mở webcam khi vừa start/reboot. Bật/tắt camera không ảnh hưởng Media.
Mất ảnh 8 giây sẽ dừng camera; sau khi cắm lại bấm Bật camera.

Cấu hình mẫu ở `~/.local/state/pi-camera/` quyền riêng; chỉ thay khi lưu mẫu.
Không ghi ảnh preview, poll hoặc chẩn đoán định kỳ ra SD. Ảnh/video là dữ liệu
ngoài release: rollback source không xóa chúng. Backup mã hóa gồm mẫu và unit,
không gồm dữ liệu camera. Deploy/rollback vẫn qua `ops/pi.ps1` và snapshot.

## Kiểm tra còn cần làm trên thiết bị

Chất lượng/đúng pha Smooth với A1 đang in, rút/cắm SSD vật lý, lưu dài hạn,
reboot, iPhone vật lý và xem từ ngoài LAN qua Cloudflare cần kiểm tra riêng.
Đã kiểm tra ghi/ghép/tải MP4 trên SSD thật, nhớ ổ qua restart agent, unmount
chặn ghi và mount lại bằng fstab rồi nhận lại đúng UUID. Đây không phải kiểm
tra rút cáp hoặc reboot vật lý.
Không coi các kiểm thử mô phỏng là đã qua các tình huống phần cứng này.
