# Dashboard 3.0 — quan sát và vận hành Pi

Triển khai ngày 12/10/2026 trên Pi Debian 13, aarch64; giữ bố cục mẫu người dùng, font Noto Sans cục bộ và light/dark. Nút GPIO đã loại khỏi phạm vi theo yêu cầu.

## Chức năng

- Đổi mạng bằng systemd transient timer, độc lập với tiến trình web. Các trạng thái: tiếp nhận, kết nối, nhận IP/chờ trình duyệt, xác nhận, thất bại, phục hồi, quá thời hạn chưa kết luận. Phiên đăng nhập và CSRF bắt buộc để xác nhận; helper kiểm tra UUID mạng đang dùng đúng đích. Nếu IP/subnet thay đổi cần tự chuyển thiết bị sang mạng mới và mở `raspberrypi.local:18765` hoặc IP Pi mới. Không coi việc nhận IP là xác nhận trình duyệt đã trở lại. Phục hồi 90 giây hiện kiểm tra trạng thái NM + IP; không bảo đảm đường đi đến thiết bị quản trị.
- `/var/lib/piwifi-events`: trạng thái thao tác và tối đa 500 sự kiện root-owned, Unicode, không ghi PSK; guard chỉ ghi khi trạng thái thay đổi. Khởi động lại dịch vụ, deploy, lưu/xóa/đổi ưu tiên Wi-Fi có sự kiện.
- `piwifi-observer.service`: thu thập mỗi 10 giây; SQLite ghi mẫu mỗi phút, giữ 7 ngày và tối đa 500 sự kiện sức khỏe. API lịch sử trả tối đa 360 điểm, lấy đỉnh từng khoảng. Chỉ giữ tên tiến trình, PID, CPU và RSS, không đọc dòng lệnh. Bộ đếm lưu lượng từ `/proc/net/dev` là tổng từ boot; tốc độ là delta giữa hai mẫu.
- `vcgencmd get_throttled`: phân biệt cảnh báo hiện tại và từng xảy ra từ boot; nguồn yếu, giới hạn xung, throttling, soft temperature limit; hiển thị xung hiện tại. Không có quyền/cảm biến thì báo chưa đọc được, không báo khỏe giả.
- Chẩn đoán mỗi phút: Wi-Fi, IPv4, ping gateway, DNS hệ thống tới `www.raspberrypi.com`, TCP `1.1.1.1:443`, cổng web trên localhost. DNS/Internet đi qua tuyến mặc định hệ thống; gateway ping gắn wlan0. Ping/TCP thất bại báo chưa kết luận. Hotspot coi gateway/DNS/Internet không áp dụng. DNS và TCP gửi các probe nhỏ đến đích cố định, không gửi dữ liệu riêng.
- Dịch vụ cho phép restart: `piwifi-web`, `piwifi-observer`, `piwifi-guard.timer`. Không có lệnh shell tùy ý, không restart NetworkManager/SSH từ UI. POST có CSRF và xác nhận trên UI.
- Bản triển khai: version, thời gian, hash SHA-256 của payload và snapshot; phục hồi latest bằng tác vụ systemd + khóa deploy. Giữ 5 snapshot sau deploy thành công; giữ dữ liệu lịch sử/sự kiện khi rollback. Snapshot chứa env bí mật, chỉ root đọc, API chỉ trả metadata. Rollback không hoàn tác apt/profile Wi-Fi.
- Source `/opt/piwifi-web` và thư viện helper `/usr/local/lib/piwifi` root-owned. Observer thinh chỉ ghi state/runtime riêng.

## MCP chỉ đọc

`mcp_server.py` dùng stdio JSON-RPC qua SSH alias `rasp-tt`; không mở thêm cổng hay tạo API token. Sáu tool: `pi_metrics`, `pi_network`, `pi_history`, `pi_events`, `pi_deployments`, `pi_operation`. Metadata readOnlyHint và allowlist client; không có thao tác ghi. Config user Codex có server `raspberry_pi`, SSH BatchMode, StrictHostKeyChecking, connect timeout. Backup cấu hình cũ nằm cạnh config dưới tên `config.toml.before-raspberry-pi-20261012`; không đưa vào repo. Cần Restart MCP server hoặc mở lại Codex nếu phiên hiện tại chưa nạp server.

MCP mất kết nối nếu Pi mất Wi-Fi; cơ chế phục hồi mạng vẫn chạy cục bộ. Khi rollback về bản trước 3.0, MCP server/observer mới sẽ không còn trong app; cấu hình client còn lại và có thể tạm tắt.

## Kiểm chứng và giới hạn

30 bài unittest: hồi quy guard/client/khóa/SSID UTF-8/auth/CSRF; thêm retention sự kiện, bucket peak, tách cảnh báo nguồn hiện tại/quá khứ, whitelist dịch vụ, operation success/fail/ack sai mạng, trang chuyển mạng, API mới và MCP read-only. Kiểm tra syntax Python/JS/bash và packaging allowlist.

Kiểm tra production: observer/web/guard active; dữ liệu `/proc`, vcgencmd và chẩn đoán mạng thật; browser theme sáng/tối, viewport 390px không tràn trang. Restart observer từ dashboard giữ mẫu lịch sử. Tác vụ systemd kết nối lại profile hiện tại đi đến confirmed khi trình duyệt xác nhận; prearm watchdog độc lập và hủy sau khi xác minh. MCP initialize/tools-list/call qua SSH và sáu tools được kiểm tra.

Không thử ngắt điện router, reboot không Wi-Fi hoặc client điện thoại thực trong đợt này; guard regression dùng mô phỏng và kết quả AP-to-Wi-Fi thực đã kiểm chứng ở V2. Không nhấn rollback production để tránh hoàn tác bản mới; kiểm tra snapshot và syntax restore. Lịch sử mới bắt đầu tại thời điểm bật observer, không thể dựng lại dữ liệu cũ.

Bản cuối được kiểm tra hoạt động sau deploy; snapshot phục hồi gần nhất `/var/lib/piwifi-deploy/20261012T113112-24065`. Đây là snapshot trước lần cập nhật cuối trong đợt 3.0; snapshot trước lần triển khai 3.0 đầu tiên `/var/lib/piwifi-deploy/20261012T112139-19282` vẫn nằm trong 5 bản giữ lại. Sáu MCP tools gọi thành công qua SSH. Thư mục test `/tmp/piwifi-v3-tests` và archive đã được dọn.

Nguồn tham khảo: https://www.raspberrypi.com/documentation/computers/os.html#get_throttled ; https://modelcontextprotocol.io/specification/2025-06-18/basic/transports ; https://developers.openai.com/codex/mcp/ . Không sao chép mã từ các dự án khảo sát.

## Sửa thông báo kết quả mạng

Theo ảnh người dùng, thông báo confirmed cũ bị lặp ý và đứng trên tiêu đề. Đã đặt phần thông báo sau header của tab mạng, trước thông tin kết nối; chỉ hiện một câu “Đã kết nối lại dashboard”, không ghép thêm message/IP cho confirmed. Trong dashboard, confirmed/recovered tự ẩn sau 15 giây tính từ updated; kết quả cũ không hiện lại khi tải trang. Trang đang đổi mạng vẫn giữ kết quả và các bước để người dùng đọc. Lỗi fetch thông thường không bị diễn giải thành một lần đổi mạng.

Đã kiểm tra JS syntax và hành vi bằng VM: kết quả cũ ẩn, kết quả mới tự hết hạn, trạng thái đang kết nối giữ hiển thị. Browser production xác minh một banner, sau header, hidden với kết quả cũ; tiêu đề trang đúng. Snapshot trước sửa: `/var/lib/piwifi-deploy/20261012T114739-29094`.
