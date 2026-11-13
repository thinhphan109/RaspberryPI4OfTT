# RobotVision gateway · 31/10/2026

Đã cài Dashboard `v1-65dc913e7c5715d7` từ kit
`/opt/pi-control-bootstrap-20261031-vision-r2b`. Bảy module khác giữ nguyên
metadata; PID Media/Browser/Camera giữ nguyên qua lần cập nhật Dashboard.

Mở `https://rasp4.thinhme.tech/robotvision/`, đăng nhập bằng tài khoản Pi
Control hiện có. Mục Ứng dụng & DNS có liên kết trực tiếp. Tunnel/DNS không đổi.

`robotvision.py` là gateway HTTP cố định đến loopback `127.0.0.1:18768`.
Chỉ mở UI/asset và các thao tác AI trong danh sách cho phép. Không proxy URL
tùy ý, không chuyển cookie Pi Control tới backend, không cung cấp model import
hoặc robot/serial/GPIO. CSRF theo session được chuyển thành token riêng của
backend ở phía server. Không ghi token vào log.

Ảnh JPEG tối đa 3 MiB chỉ áp dụng ở route RobotVision; các API khác vẫn 64 KiB.
Một inference request chờ mỗi process. Response private/no-store; camera=(self),
microphone=(). Mở trang từ tab/link ngoài hợp lệ; cross-site API/POST vẫn chặn.

Camera trình duyệt dùng getUserMedia, gửi frame JPEG về Pi khi nhận diện;
camera Pi dùng webcam USB hiện có. Nhận diện vẫn qua Ultralytics và checkpoint
`.pt`; không thêm bộ phân loại heuristic. Engine/checksum nằm trong JSON kết quả.

Kiểm tra: 310 Python fixture tests, 6 gateway tests trên runtime modular,
các JS Mobile/Interface/Catalog/Help/Feedback/Charts và bộ cài 101 file/8 module
trong fake root đã qua. Thử thật staging 8 JPEG: trung vị warm gateway 539,2 ms;
ảnh trả về trùng byte đầu vào, ảnh nền không có detection. Public Edge đã thấy
Pi camera nhận diện liên tục khoảng 1,2 FPS, AI 515 ms tại một mẫu input 320.
Không coi đó là benchmark dài hạn hoặc chứng minh iPhone/camera trình duyệt thật.

HTTP client từ Pi bị Cloudflare trả 403; không bypass. Public kiểm chứng qua
Edge đăng nhập bình thường, gateway/auth/CSRF/assets được kiểm tra thêm nội bộ.

Archive SHA `c92f46bdeeea8d34e5bff2819257a3f420824bb80e46d93f94afc033af7b5b8f`,
manifest SHA `6d14597d3e29afeada26881fe65519158b20898b352945a0d411978adee1bc01`.
Wrapper `ops/deploy-robotvision-r2b.py` đã chạy, không chạy lại destination cũ.
Bản r2 đầu đã được r2b thay thế. RobotVision vẫn là project/service độc lập.
