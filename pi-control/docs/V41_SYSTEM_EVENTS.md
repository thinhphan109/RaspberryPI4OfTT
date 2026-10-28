# 4.1.0 — Nhật ký trạng thái hệ thống

Ngày25/10/2026. Người dùng yêu cầu bổ sung log bên trong Raspberry vào Hoạt động,
sau sự cố SSD mất kết nối và phân vùng NTFS không được gắn. Bản này chỉ thêm
quan sát và hiển thị; không sửa NTFS, đổi nơi lưu camera hoặc điều khiển thiết bị.

## Nguồn và giới hạn

`system_events.py` chạy trong observer hiện có, một worker10giây; không thêm
dịch vụ hoặc quyền sudo. Userthinh hiện có nhómadm đọc journal. Query cố định
kernel, NetworkManager, các dịch vụ dự án/AdGuard/tunnel và useragentCamera/Media.
Lọc message trước ởjournal và chỉ nhận các loại lỗi/trạng thái được khai báo.
Không nhận log tùy ý của toàn bộ ứng dụng hay đọc dòng lệnh tiến trình.

Thu USBkết nối/ngắt/reset, lỗiI/O/NTFS/FAT/ext4/exFAT, nguồn/nhiệt/OOM, dịch vụ
thoát lỗi/restart, Wi-Fi thay đổi. Không coi guardoneshot Deactivatedsuccessfully
là lỗi. Tên dịch vụ và thiết bị được tách nhóm để không gộp nhầm.

Worker đọc `/proc/1/mountinfo` của host (không dùng mountinfo trong sandbox) để quan sát mountmới/mất/chỉđọc và privateIPCstatusCamera
để quan sát bắt đầu/dừng/ghép/kết quả/lỗi/bỏkhungJPEG. Chỉ gửi actionstatus,
timeout0,5s; không tạo viewer, không giữ webcam bật và không dừng phiên. Lần đầu
thấy phiên đang ghi được ghi là quan sát thấy, không dựng giờ bắt đầu giả.
Kết quả cũ không được phát lại như sự kiện mới. Không ghi từng frame/count tăng.

Sức khỏe nhiệt≥80°C, phân vùng≥90%, nguồn yếu/giảm xung và dịch vụ, cùng thay
đổi Wi-Fi/IP/DNS/Internet, được lấy từ metrics/diagnostics hiện có. Không thêm
probeInternet. Dữ liệu unknown không tự kết luận đang tốt hoặc đã phục hồi.

Lần đầu/khácboot/cursorhỏng: đọc phần journalboot hiện tại còn lưu, không quá
24giờ. Lượt tiếp dùng aftercursor. Tối đa1.000bản ghi/lượt, stdout2MiB,3giây;
vượt giới hạn báo phạm vi bị giới hạn, không tuyên bố đầy đủ logLinux. Boot được
ghi theo btimekernel, không suy đoán nguyên nhân tắt máy. Journalvolatile hiện
có không đổi; log chưa thu trước reboot không thể dựng lại sau đó.

## Lưu trữ và quyền

Đây là ngoại lệ lưu sự kiện được người dùng yêu cầu; telemetryCPU/RAM/mạng khác
vẫn ởRAM. `/var/lib/piwifi-observer/system-events.json` ownerthinh0600, thư mục
StateDirectory0700. Giới hạn2.000sự kiện/30ngày, payloadtối đa3MiB; checkpoint
atomic+fsync mỗi60giây chỉ khi thay đổi, cộng dừng bình thường. Pruner chỉ làm
bẩn dữ liệu khi thật sự có bản hết hạn. Lỗi ghi giữRAM và backoff60giây.
Mất nguồn có thể thiếu phần chưa checkpoint; lỗi lưu có thể kéo dài khoảng mất.

Lặp cùng nhóm/message/level/boot/origin cách nhau≤5phút được gộp count, giữ thời
điểm đầu/cuối và chi tiết mới nhất. Dedupecursor tránh đếm lại khi replay/restart.
Không ghi cursorđịnh kỳ nếu không có sự kiện được chọn. Không ghi từGET/polling.
Chi tiết≤800ký tự; bỏ control/ANSI, che URL/Bearer và trường mật khẩu/token/code.
Không bảo đảm bộ lọc nhận diện mọi thông tin riêng tư; trang vẫn chỉ cho admin.

Snapshot nằm trênSDvì phân vùng NTFS đang chỉđọc và SSD có thể mất kết nối; không phụ thuộc nơi
lưu video. Backup collector thêm tệp này. Source rollback giữ dữ liệu nhưng
releasecũ không đọc nhật ký mở rộng. Không thay log2ram/journald/legacySQLite.

## API và UI

`GET /api/events` giữ list200bản như trước. `?summary=1` trả events400bản mới nhất
kèm meta qua privateIPC; giữcache10giây hiện có. Merge sự kiện quản trịroot hiện
có; bộ lọc phía browser áp dụng trên tối đa400bản mới nhất này. Kho durable có
thể còn bản cũ ngoài cửa sổUI. Không có endpoint tùy ý đọc journal/file hoặc shell.

Trong Hoạt động: nguồn, mức độ, tìm không dấu, Làm mới,40dòng/lượt/Xemthêm. Một
dòng native details chứa phần kỹ thuật; giữ trạng thái mở qua refresh. Hiển thị
countlặp, loại nguồn, mức độ, timestamp. textContent cho mọi log, khônginnerHTML.
Giữ nền đen/cộtresponsive và polling30giây chỉ khi tabhiện; đổi bộ lọc/tìm/mở
chi tiết không gọiAPI hoặc ghiđĩa. Hướng dẫn dài chuyển vào Trợ giúpHoạt động.

## Kiểm tra trước triển khai

192Python checks qua: logUSB/NTFSthật, dedupe/restart/retention/cap, đọcGETkhông
ghi, retrybackoff, snapshotcorrupt/symlink, boundedcommandtimeout/size, camera
statusonly, transitionmount/health/network, auth và APIcũ. NodeUIkiểm tra filter,
tìmkhôngdấu, textantoàn/count, giữdetails và pollingẩn/hiện; các Nodecamera/
interface/feedback/charts/polling/Nonstop cũng qua. DeployDryRunallowlist qua.

Thử collector riêng trênPi trong staging: nhận logUSB03:06/11:07thật và mount
Metech3Dchỉđọc; sau bỏlogguardbìnhthường thu226sự kiện, khôngchạmgiới hạn1.000.
Lượt đọckhác đo0.185giây (không phải benchmarkdàihạn). Đọc lặp không đổi checkpoint
hoặc storagepreference; phiên camera cùngID không bị dừng. Không tạo sự cố giả,
ngắtUSB, ghiNTFS hay gửi tin nhắn để test. UIvisual/mobile/iPhonethật chưa kiểm
tra do giới hạn browser đã ghi ởV40_INTERFACE.md.

## Triển khai và kiểm tra thực tế

Đã triển khai4.1.0, release/snapshot `20261025T071413-325347`.
Chờ phiên `20261025T040741-94c6fd10` ghép đủ4.758ảnh thành video ready rồi mới
Deploy; không ngắt phiên hoặc renderer. Production9trang/215ID/14assetsHTTP200,
authAPI/metadata/legacyAPI và ảnh gốc18JPEG+downloadbyte-identical đã qua.

Kiểm tra thực tế phát hiện ProtectSystem làm /proc/self/mountinfo báo ROtrong
sandbox; ProtectHome ẩn runtimecamera. Đã sửa nguồn mountinfo sangPID1; observer
bindchỉđọc `/run/user/1000` vào `/run/piwifi-camera-runtime` và đặt biến môi trường
đường dẫnIPC. Giữ ProtectHome=true và ProtectSystem=strict, không thêm nhóm/sudoers.
Thử transientunit cùng sandbox: camera statusđọcđược, FATsda2RW/NTFSsda1ROđúng.
Nhật ký có bản đính chính hai cảnh báo sai trong giai đoạn14:02–14:09; giữ lịch sử.

Snapshotđầu177.628byte/0600;358sự kiện được giữ sau restartobserver, đọc lặp12giây
không đổi mtime. Bản cuối:390sự kiện/193.092byte/0600, restart giữ390bản và kiểm380IDgần nhất;
24giây đọcGET không đổi mtime, không còn báo lỗi khi không có log mới.
Journalctl --grep không có kết quả trả exit1/rỗng; bộ đọc chấp nhận trường hợp
này khi stdout/stderr đều rỗng. Lỗi thật có stderr vẫn báo và phục hồi cursor;
cả stdout/stderr có giới hạn byte và timeout, không lặp bootstrap khi yên.
Sáu dịch vụ dự án active; không sửa dữ liệu. SSD ngắt USB thật lúc14:09:25,
/dev/sda biến mất; nhật ký lưu đúng sự kiện USB/I/O và mất mount. Trước lúc mất
kết nối, NTFS RO/FAT RW được xác nhận; chưa biết người dùng có chủ động rút ổ.
Không tự remount/repair hoặc bắt đầu phiên quay khi ổ vắng. Rebootvật lý, iPhone và
visualbrowserchưa kiểm tra; không tuyên bố nhật ký là toàn bộ logLinux hoặc chẩn
đoán được nguyên nhân vật lý gây SSD mất kết nối.
