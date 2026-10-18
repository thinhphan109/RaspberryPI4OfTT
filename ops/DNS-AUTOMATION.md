# DNS tự động trên Windows — Dashboard 3.5

Mở lại **Pi Control** từ shortcut trên Desktop. Chế độ tự động đã được bật và
kiểm tra trên máy Windows hiện tại; DNS WiFi đang dùng `192.168.0.106`.

## Cách sử dụng

- **Bật tự động DNS**: Windows yêu cầu UAC một lần để cài/khởi động tác vụ nền.
- **Tắt tự động DNS**: dừng và xoá tác vụ. Khôi phục DNS trước khi bật nếu DNS
  hiện tại vẫn do công cụ quản lý; giữ nguyên thay đổi DNS từ bên ngoài.
- **Xem trạng thái DNS tự động**: xem IP Pi, trạng thái và lý do tạm dừng.
- Các nút đổi/khôi phục DNS thủ công sẽ tắt tự động trước để tránh hai luồng
  cùng thay đổi DNS. Bật tự động lại khi cần.

Tác vụ `PiControl-DNS-<SID người dùng>` chạy ẩn với quyền quản trị, khởi động khi
đăng nhập và tiếp tục sau khi đóng Pi Control. Không lưu mật khẩu Windows/sudo.
Mã chạy nằm trong `C:\Program Files\PiControlDNS`; không chạy tác vụ nâng quyền
từ thư mục người dùng có thể ghi. Trạng thái nằm tại
`%LOCALAPPDATA%\PiControl\dns-watch.json`, chỉ ghi khi có thay đổi.

## Cơ chế

Mỗi lượt cách nhau 30 giây cộng thời gian kiểm tra: tìm Pi qua mDNS, tên `.local`,
IP đã lưu hoặc IP lịch sử; xác minh khoá SSH và hostname rồi thử DNS trực tiếp.
Chỉ sau khi thành công mới đặt DNS IPv4 của adapter **WiFi** về IP mới.
Không quét subnet và không thay đổi adapter VPN/Ethernet.

Ba lượt thất bại liên tiếp khi DNS vẫn trỏ tới Pi do công cụ quản lý sẽ đưa DNS
về DHCP. Khi đó lọc quảng cáo tạm ngừng; khi tìm được Pi và DNS trả lời trở lại,
tác vụ tự đặt lại DNS Pi. Nếu người dùng/VPN/công cụ khác đổi danh sách DNS khi
Pi Control đang quản lý, tác vụ tạm dừng và không ghi đè. Bấm Bật tự động DNS để
tiếp tục. Cấu hình DNS gốc trước lần thử Pi-hole được giữ cho việc khôi phục.

Mạng chặn multicast/mDNS có thể ngăn tìm IP mới. Khi đó mở
<https://rasp4.thinhme.tech/#apps>, lấy IP, nhập vào Pi Control rồi bấm **Tìm Pi**.
IP đã xác minh sẽ được lưu để tác vụ dùng ở lượt sau. Dashboard qua tên miền cần
Pi có Internet; không thể khôi phục kết nối của một Pi đã mất mọi đường mạng.

Chế độ này không thay đổi DNS iPhone, DNS riêng của trình duyệt hay VPN. iPhone
vẫn cần DNS thủ công theo Wi-Fi. Khi mất Pi, có thể cần chờ khoảng 1–2 phút hoặc
lâu hơn tuỳ thời gian SSH/DNS thất bại trước khi Windows về DHCP.

## Kiểm tra trên Dashboard

Mở **Ứng dụng & Truy cập** từ chính thiết bị cần thử. Trang tự chạy một phép thử
khi mở mục này, có nút thử lại và ghi thời điểm kết quả:

- **Đã xác nhận dùng AdGuard và chặn được mẫu thử**: Pi thấy truy vấn ngẫu nhiên
  của phiên và chặn được tên miền kiểm tra trên Pi.
- **Đã qua AdGuard — mẫu thử chưa được chặn**: đường DNS đã xác nhận, cần xem bộ lọc.
- **Chưa xác nhận thiết bị đang dùng AdGuard**: chưa thấy truy vấn; có thể DNS đi
  đường khác hoặc trình duyệt chặn phép thử. Không kết luận thiết bị mất mạng.

Kết quả xác nhận đường DNS của phép thử tại thời điểm đó, có thể qua DNS trung
gian; không bảo đảm mọi ứng dụng dùng cùng DNS. Đổi mạng/IP sẽ yêu cầu thử lại.

## Bằng chứng kiểm tra

51 bài kiểm thử Linux đạt; 11 tình huống chính sách và 5 tình huống worker với
ranh giới OS/SSH mô phỏng đạt. UI Pi Control có 17 nút, hiển thị tiếng Việt đúng.
Đã chạy tác vụ thật, xác nhận `nslookup` dùng Pi, tắt trả về DHCP rồi bật lại Pi.
Trình duyệt Edge qua tên miền xác nhận truy vấn và bộ lọc. Mẫu polling Dashboard
20 giây vẫn có write_bytes tăng bằng 0. Chưa thử di chuyển Wi-Fi vật lý, tắt Pi
dài hạn, đăng xuất/khởi động lại Windows hoặc thao tác trên iPhone.
