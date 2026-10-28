# Đề xuất liên kết camera Pi với mẻ in METECH Assistant

Ngày25/10/2026. Trạng thái: đề xuất khảo sát, chưa triển khai hoặc bật thông báo.

## Cơ sở trong mã nguồn hiện tại

Đã đọc workspace `D:/1. WorkSpace/ZaloBotTroLyofTT`, package1.30.19; chưa kiểm tra
version production. Bot có sẵn Bambu Cloud telemetry, liên kết
`deviceId + jobKey + batchId`, lịch sử `bambu-print-sessions` và luồng ảnh camera
Cloud khi mẻ hoàn thành. Binding kiểm tra dữ liệu mới, job hiện hành và mã mẻ
cố định; completion kiểm tra lại đúng máy/job. Kênh nhận ảnh cần quyền camera
và tùy chọn cameraOnDone. Chưa thấy cầu nối camera Raspberry trong phần đã đọc.

Nguồn kiểm tra:
- `src/modules/print3d/bambu-cloud.js`: bind, captureLinkedSession, finishBinding.
- `src/modules/print3d/cloud-sessions.js`: lưu và phát sự kiện theo job.
- `src/modules/print3d/bambu-camera.js`: ảnh Cloud gắn mẻ/job, completion, quyền nhận.
- `src/surfaces/bambu-cloud.js`: API dashboard có đăng nhập, binding và camera.
- `docs/RELEASE-V1.30.19.md`: lịch sử phiên, sự kiện độc lập, không coi mất mạng là kết thúc.

Pi Control4.0.4 có phiên webcam, JPEG/MP4 trên SSD, trạng thái recording/rendering,
gallery và API dashboard có đăng nhập/CSRF. Session hiện chưa chứa mã mẻ/job.
API dashboard hiện tại chưa phải API giao tiếp máy–máy.

## Phương án đề xuất

Bot tiếp tục quản lý mã mẻ và phiên máy. Pi nhận thông tin liên kết và quản lý
quay/ảnh/video. Gắn vào giao diện mẻ và trang Camera hiện có, không thêm trang
quản lý mẻ riêng. Một mẻ có thể có nhiều phiên quay do thử lại hoặc camera lỗi.
Nguồn ảnh “Camera máy in” và “Webcam Pi” hiển thị rõ; không âm thầm đổi nguồn
hoặc gắn ảnh của job khác khi một nguồn không truy cập được.

Mỗi liên kết lưu `printerId/deviceId`, `jobKey`, `batchId`, `cameraId`,
`cameraSessionId` và phiên bản liên kết. Không ghép theo tên file hoặc thứ tự
dòng Sheet. Thay mẻ/job không được chuyển video cũ sang liên kết mới.

Worker nhỏ trên Pi chủ động gọi HTTPS tới bot. Đề xuất API riêng với long-poll
sự kiện, xác thực token có phạm vi theo Pi/máy in và thu hồi được. Không cần mở
cổng router, IP Pi cố định hay thêm Tailscale; khi đổi mạng, worker nối lại khi
có Internet. Bot gửi lệnh trong phản hồi của kết nối Pi mở ra; không public
socket camera hoặc bỏ đăng nhập dashboard. Ghép thiết bị một lần từ dashboard
chủ sở hữu; không chuyển token Zalo/Bambu/Google Sheets sang Pi.

## Hai bước triển khai

1. Liên kết thủ công đúng một lần: chọn mẻ đang liên kết với job máy trong bot,
   gắn với phiên Pi đang quay hoặc phiên mới. Hai dashboard hiện cùng mã mẻ,
   tên file, trạng thái camera và nút mở ảnh/video có kiểm tra quyền. Chưa tự
   bắt đầu/kết thúc. Kiểm tra metadata, restart, đổi mạng và chống gắn nhầm trước.
2. Sau khi bật tùy chọn tự quay cho máy: sự kiện job mới hợp lệ bắt đầu phiên;
   FINISH kết thúc/ghép đúng phiên. Tận dụng hàng đợi thông báo hiện có khi người
   dùng bật nhận ảnh/video, không tự mở rộng người nhận.

Điều kiện tự bắt đầu: đúng máy/job/liên kết, dữ liệu mới, camera không bận, mẫu
vị trí hợp lệ nếu dùng Position, SSD đã chọn đang gắn và còn dung lượng. Bỏ qua
sự kiện cũ lúc worker vừa kết nối; trường hợp muốn tham gia job đang in cần thao
tác rõ. Không dừng phiên thủ công hoặc tự chiếm camera để bắt đầu job khác.

FINISH chỉ tác động đúng job/session; FAILED kết thúc hoặc giữ phần đã chụp
theo chính sách lựa chọn, ghi nhãn in lỗi. PAUSE giữ liên kết và phiên; mất mạng
không suy ra FINISH. Pi tiếp tục phiên đang quay trong giới hạn dung lượng/thời
gian hiện có, nối lại thì đối chiếu sự kiện và phiên thực tế. Không dùng trạng
thái ghép video để chốt số lượng thành công hay thay dữ liệu sản xuất trên Sheet.

## Dữ liệu, quyền và kiểm chứng

- JPEG/MP4 chính giữ trên SSD; bot giữ metadata và liên kết. Không gửi từng
  frame qua Internet. Ảnh đại diện hoặc video chỉ tải lên khi được yêu cầu/chọn.
- Xem/tải từ bot đi qua kiểm tra quyền và token ngắn hạn hoặc proxy; không phát
  liên kết file công khai vĩnh viễn. Gửi Zalo dùng quyền/tùy chọn/hàng đợi sẵn có.
- Outbox sự kiện có eventId, thứ tự và xác nhận; start/stop lặp lại không tạo
  phiên trùng hoặc dừng nhầm. Restart cần đối chiếu mapping và trạng thái agent.
- Long-poll/heartbeat không ghi SQLite/config định kỳ trên Pi; chỉ chốt mapping
  và xác nhận ở bước chuyển trạng thái cần phục hồi. Có retry/backoff khi offline.
- Test: liên kết muộn, cùng tên tệp khác job, hai mẻ, replay/restart, job đổi nhanh,
  stale/mất mạng, SSD mất, camera bận, ghép thất bại, quyền bị thu hồi và tải video.
  Dùng dữ liệu giả trước; không gửi tin thử vào nhóm thật khi chưa được cho phép.

Liên kết Bambu Cloud giúp tự biết bắt đầu/kết thúc và gắn đúng mẻ. Nó không tự
đảm bảo đầu in/bàn đã đỗ đúng vị trí cho từng ảnh. Chế độ Position vẫn cần mẫu
đúng và kiểm tra thực tế; không dùng sự kiện đổi lớp làm bằng chứng đã đỗ đầu in.

Ưu tiên bước1 để kiểm chứng mapping và trải nghiệm, sau đó bước2 cho tự động hóa.
Chưa thay source/runtime bot hoặc cấu hình Pi; chưa gọi API ngoài hay gửi Zalo.
