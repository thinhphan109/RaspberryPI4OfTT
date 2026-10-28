# 3.14.3 — Xem ảnh gốc của phiên

Mỗi phiên trong Video & ảnh gốc có nút Xem ảnh. Dialog cùng giao diện nền đen,
ảnh lớn, trước/sau, phím mũi tên, range có debounce150ms, ô nhảy ảnh300ms/Enter
và tải JPEG gốc. Không thumbnails/preload hoặc polling ảnh; lấy snapshot danh
sách khi mở, chỉ tải ảnh đang chọn, hủy request cũ và bỏ kết quả đến sau đóng.
Mobile giữ đúng 16:9 để tránh khoảng đen thừa; không đổi layout các mục khác.

Dialog tạm dừng preview/status/library/heartbeat của tab và release viewer;
ghi timelapse vẫn giữ camera theo chính sách hiện tại. Đóng trở lại lịch xem;
pagehide/đổi mục đóng dialog và không mở lại timer trong nền. Escape native.

GET có xác thực `/api/camera/photos/<id>?storage=…` trả indices thực tế, tối đa
20.000 ảnh; bỏ ảnh bị thiếu, symlink và tên không hợp lệ. GET
`/api/camera/photo/<id>/<index>?storage=…` trả JPEG, thêm `download=1` để tải.
IPC photos/photo riêng, không đưa vào POST allowlist. Dò USB đang mount trước
đọc, mở mount/root/session/file qua dirfd+O_NOFOLLOW, kiểm tra device, manifest
và regular file; JPEG tối đa2MiB. Không tạo thư mục hoặc ghi cấu hình/dữ liệu;
no-store/nosniff trên response. Không nhận đường dẫn file do browser cung cấp.

161 Python tests passed, gồm thiếu ảnh, thứ tự có khoảng trống, symlink,
session/manifest/index/storage không hợp lệ, giới hạn JPEG, auth/headers và
đọc không đổi cấu hình. Node camera lifecycle/gallery actual-index navigation,
download, không polling, stale-response cleanup/BFCache và polling/charts đều
qua. Browser bản loopback dùng chính source mới và ảnh thật, chỉ đọc: desktop
1366×900, mobile390×844 không tràn ngang; trước/sau, jump Enter, range Home,
arrow và Escape đã thử. Mobile dialog556px cao trong viewport844px.

Production HTTP thật đã đọc ảnh đầu/cuối và tải byte-identical JPEG trên SSD
phiên20261024T141247-12266de8; invalid index/session và anonymous bị từ chối,
mtime storage preference không đổi. Dịch vụ web/observer/guard/AdGuard và
user camera/Media đều active. Không tạo bản ghi mới hoặc điều khiển máy in để
kiểm thử thư viện. Reboot/iPhone thật/rút cáp khi đang xem vẫn chưa thử.

Release/snapshot cuối: `20261024T142829-185465` (bao gồm chỉnh gọn mobile).
Ảnh chụp QA nằm trong ops/reports/camera-gallery-20261024-{desktop,mobile}.png
(local ignored); bản thử loopback và tunnel đã dọn sau kiểm tra.
