# 3.14.4 — Tiếp tục phiên khi webcam gửi JPEG lỗi

Lỗi thực tế do người dùng báo: phiên chụp theo vị trí chạy khoảng29giây rồi
dừng, `error=broken data stream when reading image file`; last_result có
modeposition, frames0, stateincomplete. Status lúc kiểm tra vẫn availableTrue.
JPEG giải mã lỗi trong fingerprints trước đây rơi vào exception chung của tick,
gọi stop và ghép; chưa có ảnh nên cuối phiên báo không đủ2ảnh.

Đã tách lỗi giải mã khỏi lỗi ổ lưu/capture. Position bỏ qua JPEG giải mã lỗi,
xóa scores và reset thời gian ổn định bằng mẫu không hợp lệ, giữ session để chờ
khung tiếp theo. Interval giải mã nghiêm ngặt trước khi ghi ảnh đến hạn; bỏ
khung lỗi mà không đánh số ảnh mới hay đẩy deadline. Bộ đếm dropped_frames ởRAM,
note phiên giải thích đang tiếp tục. Không bật LOAD_TRUNCATED_IMAGES hoặc tạo
ảnh giả. Lỗi mất ổ, hết chỗ, giới hạn hoặc mất webcam vẫn dừng như trước.
Calibration lỗi trả thông báo lấy ảnh mẫu mới trước khi thay reference/config.

164 Python tests passed, gồm OSError đúng thông báo người dùng trong position:
session vẫn giữ, không render, khung sau xử lý tiếp; JPEG lỗi interval không ghi,
JPEG tốt sau đó ghi frame000000; mẫu lỗi không thay calibration. Deploy
release/snapshot20261024T144207-189369. Status sau cài error rỗng, không ghi/ghép.
Chưa quan sát phiên position dài với A1 in thật sau bản sửa; không kết luận
webcam/cáp/power là nguyên nhân phần cứng khi chưa có bằng chứng.
