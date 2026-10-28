# Dashboard 3.12.1 — nhãn đồ thị và chốt ngày

Release/snapshot `20261018T173849-312422`, ngày19/10/2026 giờ Việt Nam.

## Nhãn tương tác

PiCharts.inspect dùng dữ liệu đã có ở trình duyệt cho4đồ thị: mạngRX/TX,
lịch sửCPU/RAM/nhiệt độ, tốc độ ghiSD và dung lượng ghi theo ngày.
Di chuột/bấm chọn hiển thị tooltip thời gian + giá trị, đường dọc và điểm màu;
nhãn theo con trỏ và giới hạn trong viewport. Không thêm request hoặc ghi server
khi tương tác. Pointer events hỗ trợ chạm/kéo ngang, touch-action pan-y giữ cuộn
dọc. SVG focus được, dùngLeft/Right/Home/End vàEscape. Tooltip không nhận click.

Chọn mẫu gần nhất, không nội suy giá trị qua đoạn thiếu dữ liệu; null hiển thị
Không có mẫu, giá trị0 vẫn là0. Ngày bị gộp được ghi rõ Nhóm ngày/mốc cuối.
Nhãn ẩn khi rời đồ thị bằng chuột, chuyển tab, cuộn/resize hoặc trang bị ẩn.
Giữ nền đen, màu riêng từng series và trục số. Không mở rộng ra sparkline CPU
nhỏ ở Tổng quan vì dữ liệu đó không có các mốc thời gian thật như đồ thị lịch sử.

## Ngày và checkpoint

Ngày vẫn là00:00–24:00 giờ Việt Nam, độc lập uptime/session. Bộ đếm boot là chỉ
số riêng. Giữ checkpoint5phút và graceful-stop; thêm checkpoint khi mẫu đi qua
biên ngày, ở lượt lấy mẫu đầu tiên sau00:00. Khoảng bắc qua biên được phân bổ
theo thời gian như3.12. Không thay thành chỉ lưu một lần/ngày để tránh mất cả
ngày khi nguồn bị ngắt. NếuPi offline lúc00:00, xử lý khi observer hoạt động lại.
Không thể biết phần ghi chưa checkpoint của boot cũ đã mất khi cúp điện.

## Kiểm chứng

124Python checks qua, gồm kiểm tra mới chốt hai phía biên ngày trước khi đủ5phút.
Node chart tests qua: hình học, gap/null, nearest timestamp, không biếnnullthành0.
Trên production: mouseclick hai vị trí SD ra hai nhãn khác; RX/TX đủ2giá trị;
lịch sử tài nguyên đủ3series, nullCPU hiển thịKhông có mẫu; daily có lượngMiB.
Ở390px tooltip nằm trong viewport, không tràn ngang. Keyboard chuyển mẫu hoạt động.
Viewport trả mặc định. Chưa thử kéo bằng ngón tay trên iPhone thật hoặc quan sát
mốc00:00thật; phần này mới có handler pointer/unit test biên ngày.
