# Kiểm tra tài nguyên và lưu trữ — 12/10/2026

Phạm vi: đo Pi thật, đối chiếu mã nguồn, đề xuất tối ưu. Không triển khai thay đổi app, swap, mount hoặc journald trong đợt kiểm tra này. Script đo đọc tại `ops/performance_audit.py`; chạy bằng Python trên Pi với sudo để xem PSS và I/O của các process. Script tạm trên `/tmp` đã dọn.

## CPU và RAM

Ba khoảng 30 giây liên tiếp, tổng 90,14 giây, dashboard được truy cập trong thời gian đo. CPU theo cgroup bao gồm công việc con chạy trong cgroup; 100% là một nhân, Pi có 4 nhân. Guard là oneshot, không nằm trong hai service dài hạn được đo nên tổng không bao gồm mọi lần chạy guard. Đây không phải benchmark tải cao hoặc trung bình 24 giờ.

| Dịch vụ | CPU trung bình, 1 nhân = 100% | CPU theo tổng 4 nhân | RAM PSS ở cuối phép đo |
|---|---:|---:|---:|
| piwifi-web | 5,53% | 1,38% | 36,87 MiB |
| piwifi-observer | 1,78% | 0,44% | 9,51 MiB |
| Tổng hai dịch vụ | 7,31% | 1,83% | 46,38 MiB |

RSS cộng dồn: web 58,39 MiB, observer 16,21 MiB; RSS đếm trùng trang chia sẻ của master/worker, nên dùng PSS cho ước lượng RAM riêng. Máy có khoảng 3,70 GiB RAM; MemAvailable lúc kiểm tra khoảng 2,50 GiB. Tải hiện tại của dashboard nhỏ, còn dư tài nguyên cho phát triển.

Các khoảng CPU web lần lượt 9,491%, 2,803%, 4,296% của một nhân; observer 1,095%, 3,037%, 1,197%. Số GET quan sát trong một phút riêng: metrics18, events6, operation7, status4, history2, deployments2. Số client/tab và thời điểm quan sát ảnh hưởng kết quả.

## Ghi SD và nguyên nhân SQLite

- Block device `mmcblk0` tăng 540.672 byte ghi trong 90,14 giây (0,516 MiB). Ba khoảng: 151.552, 229.376, 159.744 byte.
- Process tồn tại xuyên suốt phép đo: gunicorn worker 360.448 byte, observer 49.152 byte, ext4 journal thread 114.688 byte. Không cộng các bộ đếm này để suy ra NAND: attribution process và block device khác lớp, process sống ngắn có thể không xuất hiện.
- Nếu duy trì y hệt mức này 24 giờ: khoảng494 MiB/ngày (~0,48 GiB). Đây chỉ là ngoại suy ngắn, không phải số đã đo24 giờ, TBW hay write amplification nội bộ NAND.
- Snapshot metrics trong `/run` đã là tmpfs: 5 lượt `observer.current()` ghi0 byte, thời gian tổng1,12 ms.
- 5 lượt events reader:163.840 byte (160 KiB),8,2 ms. 5 lượt history reader:163.840 byte,8,3 ms.
- 5 lượt reader `mode=ro` nhưng mở/đóng mỗi lần vẫn ghi147.456byte trong lần thử; chỉ thêm read-only chưa loại hết tạo WAL/SHM.
- Giữ một SQLite connection làm anchor, rồi lặp5 lượt events,5 lượt history,5 lượt read-only: từng nhóm ghi0 byte theo `/proc/self/io` của process thử. Đóng anchor lúc đó cũng0 byte. Đây là thí nghiệm đọc; không chứng minh writer hoặc toàn Pi sẽ không ghi.

`observer.connect()` hiện được dùng cả đọc lẫn ghi: mỗi lần mở lại WAL, chạy CREATE TABLE IF NOT EXISTS, rồi đóng connection. WAL/SHM nằm trên SD; thời gian tồn tại ngắn tạo ghi phụ dù chỉ đọc. Theo SQLite, last connection close cũng có thể checkpoint. Đây là điểm tối ưu ưu tiên, lớn hơn lượng dữ liệu JSON thuần trong sample.

## Tình trạng thẻ và filesystem

- Thẻ type SD,59,6 GiB (~64 GB), mã GC2QT, manfid 0x1b, oemid 0x534d, tự báo ngày 09/2018. Không xác minh được SKU/loại NAND/endurance từ các trường này; không biết lịch sử dùng trước khi cài Pi.
- `life_time`, `pre_eol_info` không có. SD không có health chuẩn tương đương các trường eMMC; không tính được phần trăm hao mòn hoặc số năm còn lại.
- Kernel boot hiện tại: không thấy I/O error, Buffer I/O, EXT4-fs error hoặc mmc error/timeout theo bộ lọc. Không phải kiểm tra toàn bề mặt NAND.
- ext4 superblock: state clean, tạo 06/10/2026, Lifetime writes8 GB. Giá trị của filesystem này, không phải tổng lifetime NAND của thẻ. Filesystem đang mounted read/write; không chạy fsck sửa lỗi trên root đang mount.
- SQLite `PRAGMA quick_check` trảok.
- Root đã `noatime`; filesystem metadata_csum/has_journal bật. Root còn khoảng49 GiB trống.
- Journald effective drop-in `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`:Storage=volatile. Khoảng12 MiB journal nằm `/run/log/journal`, `/var/log/journal` chỉ4 KiB. rsyslog inactive dù journald có ForwardToSyslog=yes. Không có lợi ích từ việc cài thêm log2ram lúc này.
- Swap active là zram2 GiB, dùng0. Có backing `/dev/loop0` -> `/var/swap` trên SD; zram bd_stat0 / 0 / 0, chưa writeback trong boot này. Không kết luận zram luôn không ghi SD. Giữ dự phòng lúc này để tránh OOM khi tải sau này tăng.
- Observer state16 KiB, database12 KiB tại phép đo; events16 KiB,5 snapshot deploy4,6 MiB. Retention giới hạn dung lượng nhưng không tự loại ghi nhỏ thường xuyên.

## Phương án tối ưu đề xuất

### Giai đoạn1: tối ưu app, giữ chính sách dữ liệu

1. Observer giữ một kết nối ghi dài hạn, khởi tạo schema/WAL một lần. Web/MCP dùng kết nối đọc riêng mode=ro, không khởi tạo schema. Chọn checkpoint có giới hạn dung lượng/thời gian; không tạo/đóng WAL/SHM theo mỗi HTTP request.
2. Giữ metrics snapshot trên RAM; cache dữ liệu event/history cho UI, chỉ refresh khi tab liên quan đang mở. Ghép việc đọc snapshot metrics đang trùng5/10 giây. Giữ poll tiến trình3 giây chỉ lúc có thao tác đổi mạng. Chia sẻ cache status cho nhiều client, invalidation sau mutation.
3. Batch đọc trạng thái5 unit thay5 tiến trình systemctl riêng; cache profiles khi không thay đổi. Giảm hoặc bỏ access log GET thành công; vẫn giữ lỗi/app security events. Log hiện ởRAM nên bước này giảm overhead và nhiễu, không phải nguyên nhân SD chính.
4. Đo lại cùng workload90 giây, sau đó khảo sát24–48giờ. Tiêu chí: các route chỉ đọc không tạo thêm write_bytes dưới steady state; lịch sử vẫn còn sau restart, guard/CSRF/ack hoạt động; dữ liệu stale được hiển thị đúng.

### Giai đoạn2: chế độ tiết kiệm SD, có đánh đổi rõ

- Thu thập10–30 giây, giữ mẫu lịch sử1 phút, gom5 mẫu trong RAM rồi commit mỗi5 phút. Từ1.440 xuống 288 commit/ngày: giảm80% số commit; không hứa giảm80% số byte vật lý.
- Flush khi service dừng bình thường; khi mất điện đột ngột có thể mất tối đa khoảng5 phút mẫu chưa flush. Database/retention7 ngày vẫn trên SD. Sự kiện mạng/cấu hình quan trọng giữ cơ chế ghi bền riêng; không đưa `/etc/NetworkManager/system-connections` hay env bí mật vàoRAM.
- Ban đầu giữ SQLite FULL. Chỉ đánh giá NORMAL riêng cho dữ liệu telemetry nếu chấp nhận khả năng mất các commit gần nhất trước checkpoint khi mất điện; không dùng synchronousOFF hoặc bỏ journaling toànfilesystem.
- Giữ journald volatile và noatime đã có; cân nhắc giới hạn journal RAM. Không xóa swapbacking chỉ dựa trên tải nhẹ hiện tại.

### Giai đoạn3: bảo vệ dữ liệu và phần cứng

- Backup cấu hình và dữ liệu cần giữ ra PC/ổ ngoài; snapshot cùngSD không bảo vệ khi thẻ hỏng. Env chứa mật khẩu/secret cần backup riêng có bảo vệ, không xuất vào report.
- Thẻ tự báo 2018 đã cũ: chuẩn bị thẻ thay thế chất lượng/endurance rõ ràng sau backup nếu vận hành24/7. Chưa có bằng chứng nó đang hỏng. Nếu phát triển nhiều app/database/log, chuyển root/data sangSSD USB hoặc data riêng trên SSD là hướng dài hạn.
- Nguồn ổn định và shutdown đúng; UPS khi hay mất điện. Overlayroot chỉ đánh giá khi dự án ổn định và có vùng dữ liệu/config persistent riêng; hiện còn deploy và đổi Wi-Fi thường xuyên nên chưa bật.
- Thêm chỉ số ghiSD/ngày và zram writeback trên dashboard; ghi rõ health SD không có số %, counter ghi chỉ phản ánh host/boot, không tuổi thọNAND.

## Tài liệu đối chiếu

- SQLite WAL/lastconnection/checkpoint: https://www.sqlite.org/wal.html
- SD không có health chuẩn như eMMC: https://kernel.googlesource.com/pub/scm/utils/mmc/mmc-utils/+/c6692d5f9bf1ab6fbf5694a0b61477621cc4d016
- RaspberryPi filesystem resiliency: https://pip-assets.raspberrypi.com/categories/685-whitepapers-app-notes/documents/RP-003610-WP/Making-a-more-resilient-file-system
- zram writeback/bd_stat: https://www.kernel.org/doc/html/latest/admin-guide/blockdev/zram.html
