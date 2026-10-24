# 3.14.2 — Lưu camera trên SSD

Chọn nơi lưu trong Camera ghi nhớ UUID phân vùng qua restart agent. Status trả
`storage_default` theo mount hiện tại và `storage_uuid`. POST `storage` vẫn theo
xác thực/CSRF hiện có; chỉ nhận RAM hoặc một phân vùng USB đang mount có đủ
dung lượng. Không đổi khi đang ghi/ghép. Chỉ ghi cấu hình khi lựa chọn thay đổi;
polling không ghi. Backup state camera hiện có bao gồm `storage.json`.

Ghi từ UI không truyền đường dẫn cũ: agent dò lại USB và giải UUID ngay trước
khởi tạo phiên. Nếu SSD đã nhớ vắng mặt, UI khóa nút ghi và agent từ chối;
không tự chuyển RAM, SD hoặc ổ USB khác. Có thể chủ động chọn RAM để thử.
Thư viện và các thao tác với phiên cũ giữ API hiện tại.

SSD Samsung PM991 qua JMS583, phân vùng NTFS Metech3D, UUID
`01DD5FF0C7B1A200` đã mount `/mnt/pi-camera-ssd`. `/etc/fstab` dùng ntfs3,
nofail, noatime, uid/gid1000 và device-timeout5s. Phân vùng FAT32 không đổi;
không format hay chuyển hệ điều hành khỏi SD. USB hiện đàm phán 480M.
Backup fstab gốc: `/var/lib/pi-camera-ssd/20261024T140411Z/fstab.before`;
backup trước khi chuyển khỏi mount desktop:
`/var/lib/pi-camera-ssd/20261024T140840Z/fstab.before`.
Rollback Dashboard không hoàn tác cấu hình mount hoặc xóa dữ liệu SSD.

156 kiểm thử Python và Node camera/polling/charts đã qua. Thử thật qua HTTP
có đăng nhập/CSRF: 4 JPEG từ webcam → MP4 61.956 byte, tải thành công trên SSD;
restart agent vẫn nhớ UUID và liệt kê video. Thử unmount ổ đang rảnh: ghi mặc
định bị từ chối, thư mục bên dưới trên SD không đổi; mount lại bằng fstab và
agent nhận lại đúng UUID. Kiểm tra kernel không thấy lỗi I/O mới, throttled=0x0.

Mount desktop `/media/thinh/Metech3D` bị udisks xóa thư mục khi unmount nên đã
chuyển sang mount riêng `/mnt/pi-camera-ssd`; dữ liệu volume không thay đổi.
`findmnt --verify` không có lỗi; cảnh báo ntfs3/on-disk ntfs chỉ là tên driver
và định dạng do blkid báo. Không thử reboot hoặc rút cáp vật lý, ghi dài hạn,
iPhone thật, hoặc độ chính xác theo lớp khi A1 in.

Release/snapshot: `20261024T140449-179475`. Sau thử nghiệm camera về nghỉ;
kiểm tra cuối có 1 người xem nên tự bật lại đúng chính sách, không ghi/ghép.
Cách dùng và lệnh mount/tháo an toàn: `ops/CAMERA.md`.
