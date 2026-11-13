# Wi-Fi fallback: rà soát và khôi phục ngày 02/11/2026

## Trạng thái thực tế

**Đã deploy và kiểm tra trên Pi ngày 02/11/2026.** Pi đã khôi phục kết nối tới
`iP of TT` tại `172.20.10.5`. Bộ khôi phục offline chạy thành công, quyền profile
mới là root:root 0600, cmdline được hoàn nguyên đúng checksum và payload tạm đã xóa.
Network `v1-ffcc192dfc5c1572`, Dashboard `v1-c0cdd47f6371c7df` đang hoạt động.

Lần kiểm tra trước thấy Pi kết nối TPWork không chứng minh fallback trước đó đúng:
người dùng xác nhận đã tự sửa cấu hình trên ổ đĩa để có lại kết nối. Chưa có log
trước can thiệp để kết luận chính xác nhánh lỗi đã xảy ra.

Windows nhận SSD JMicron serial `1234A3`, dung lượng 128035676160 byte, bootfs H:,
root PARTUUID `9586d7bf-02`; người dùng xác nhận đây là SSD cần sửa, không phải SD.
Trong lúc chỉ đọc, SSD tự mất kết nối; người dùng xác nhận không chủ động rút.
Windows ghi nhiều sự kiện disk 153, I/O phải thử lại, gồm LBA 0. Chưa phân biệt
được lỗi cáp, adapter, cổng/nguồn USB, firmware hay SSD. Không quy sự cố này cho
phần trăm hao mòn cũ và không khẳng định đây là nguyên nhân lần mất hotspot.

Sau khi cắm lại trực tiếp: sáu lượt đọc kernel và kiểm tra nhận diện ổ đều đạt,
không có lỗi disk mới trong khoảng theo dõi ngắn. Đây có thể là đọc qua cache,
không thay cho kiểm tra phần cứng dài hạn. FAT có cờ dirty; CHKDSK chỉ đọc báo
không phát hiện lỗi cấu trúc file. Không chạy /f, /r, format hoặc sửa ext4.

## Lỗ hổng trong guard cũ và bản sửa

- Tên `GENERAL.CONNECTION` có thể xuất hiện khi profile còn chuẩn bị, chờ xác
  thực hoặc DHCP. Guard cũ coi tên này là kết nối thành công và trả `preserved`.
  Bản sửa yêu cầu trạng thái thiết bị 100, profile thực và IPv4 hợp lệ; không
  coi IPv4 link-local, loopback, unspecified hoặc multicast là kết nối quản trị.
- Guard cũ chỉ xử lý mất kết nối ở trạng thái 30. Trạng thái đang kết nối bị kẹt
  được giữ mãi; trạng thái failed 120 cũng không chuyển AP. Bản sửa chờ tối đa
  90 giây tính từ lượt quan sát đầu tiên, dùng monotonic và giữ mốc qua các lượt
  timer, kể cả khi tên profile thay đổi. Quá hạn hoặc failed thì yêu cầu AP.
  Thời gian phát hiện thực tế còn phụ thuộc boot, timer và thời lượng lệnh NM.
- Sau khi nmcli timeout, tên profile có thể còn tồn tại. Mọi nhánh giữ kết nối
  mới đều kiểm tra trạng thái + IPv4, không chỉ tên. Giới hạn hai profile mỗi lượt
  trước AP, kiểm tra lại trước khi chuyển để giữ kết nối vừa hoàn tất.
- Sau khi bật AP hoặc tự trở về Wi-Fi, kiểm tra kết quả thực. Lỗi AP được báo
  `error` và tiến trình trả mã 1 thay vì systemd ghi thành công khi thao tác lỗi.
- Giữ chính sách AP có client/không đọc được client, hai lượt trống, grace 120s,
  quét AP thất bại thì giữ AP và khôi phục AP nếu trở về Wi-Fi thất bại.
- Không tự bật radio bị tắt, đổi quyền quản lý thiết bị, khởi động lại NM, sửa
  profile cũ hay coi mất Internet là lý do ngắt một LAN vẫn truy cập được.
- Helper cố định `LC_ALL=C` khi chạy lệnh để phân tích kết quả nmcli ổn định.

Nguồn đối chiếu:
[NetworkManager device states](https://networkmanager.dev/docs/api/latest/nm-dbus-types.html),
[nmcli và locale](https://networkmanager.dev/docs/api/latest/nmcli.html).

## Bộ khôi phục offline đã ghi vào bootfs

`ops/prepare_offline_wifi.py` đọc mật khẩu qua getpass, tạo PSK WPA2 dẫn xuất;
không ghi mật khẩu vào source, tham số dòng lệnh hay báo cáo. PSK vẫn là thông tin
đăng nhập và file payload tạm chỉ ở bootfs, sẽ bị xóa khi runner thực thi.

`ops/offline_wifi_boot.py` chạy một lần bằng systemd-run-generator:

1. Xác minh root UUID `98a7c93a-53ab-4f91-b51e-0bbccfc1fff2` và fingerprint SSH
   đã được người dùng xác minh ở lần cài SSD; sai nhận diện thì không sửa NM.
2. Xác minh checksum, thêm profile Wi-Fi mới cho `iP of TT`, quyền 0600 trên Linux.
   Không ghi đè profile có nội dung khác, không xóa profile TPWork hoặc Wi-Fi nhà.
3. Khôi phục nguyên byte cmdline cũ, xóa script/payload tạm, ghi kết quả không có
   thông tin đăng nhập vào `pi-control-net-recovery.result.json`, rồi reboot.
4. Khi backup/plan bị hỏng, chỉ gỡ đúng các tham số do bộ khôi phục thêm. Nếu
   không gỡ được an toàn thì failure action là none để tránh reboot vô hạn.

Cmdline gốc SHA256:
`4003fea20d35faaa90caf1f238510cf65dac386da2b0e742705dc7b55b33b4f3`.
Runner đã ghi SHA256:
`a71ca7c6bf663d160b2fbabf16410939be4605e416ae28a70515b2f56b38dc52`.
Kiểm tra lại script, payload checksum, LF và cmdline sau ghi đều đạt.
Sau đó đã xác minh boot thật: runner báo thành công và SSH vào được Pi ở IP mới.

Nếu cần hoàn nguyên trước khi boot: phục hồi file cmdline gốc trong
`ops/reports/fallback-20261102/cmdline-original.txt` lên đúng bootfs của SSD đã
xác minh, rồi xóa đúng các file `pi-control-net-recovery.*` được tạo bởi bộ này.
Không dùng đường dẫn ổ Windows cũ nếu chưa nhận diện lại thiết bị.

Tham khảo [systemd-run-generator](https://www.freedesktop.org/software/systemd/man/latest/systemd-run-generator.html).

## Kiểm chứng và bước tiếp

- Tái hiện ba tình huống trên guard từ Git HEAD: profile đang kích hoạt bị giữ
  nhầm, failed không bật AP, timeout còn tên profile làm bỏ qua AP. Cả ba tình
  huống thất bại như dự đoán (9 assertion failures, không có lỗi fixture).
- 30 kiểm thử logic guard mới đạt, gồm chính sách AP trước đây chuyển từ
  test_dashboard sang test_fallback_logic để chạy độc lập Flask/Linux.
- 10 kiểm thử bộ khôi phục offline đạt: đúng/sai ổ và key, checksum, không ghi
  đè profile, khôi phục cmdline, payload hỏng, thiếu plan, chống lặp boot.
- Python syntax, JavaScript syntax và polling lifecycle đạt.
- Sau khi khôi phục SSH: 333 kiểm thử ứng dụng đạt trên ARM với fixture runtime
  được cô lập; 10 kiểm thử offline recovery đạt trên ARM. Bundle 101 file/8 module,
  fake-root installer 10 unit, AdGuard check-config đạt; không cài host ở lượt thử.
- Đã chạy guard mới trực tiếp với đầu ra nmcli thật trong chế độ chặn mọi lệnh
  kết nối: đọc đúng connected100, IPv4 và trả preserved. So với live cũ, Dashboard
  chỉ khác dashboard.js; Network khác hai helper, catalog và installer recipe.
- Sudo được người dùng làm mới. Wrapper cố định digest giữ khóa mạng lúc cài,
  chỉ cập nhật Network và Dashboard, không đổi nội dung profile. Sáu metadata
  module còn lại và PID Media/Browser/Camera được giữ. EdgeVision PID1378,
  Camera PID1379 cũng giữ qua triển khai và thử mạng.

## Thử nghiệm phần cứng và kết quả cuối

`ops/test-fallback-live.py` đã chạy **một lần** từ bản root-owned trong `/run`:

1. Lưu giá trị tự kết nối và checksum profile, đặt timer khôi phục độc lập 120s
   và xác minh timer active trước khi chuyển mạng.
2. Chỉ trong RAM, tạm tắt eligibility tự kết nối của các profile Wi-Fi để mô
   phỏng không có mạng đã lưu phù hợp. Không sửa file profile trên SSD. Ngắt
   kết nối rồi chạy **guard đã cài**, không gọi bật AP trực tiếp.
3. Guard trả `fallback / known-wifi-unavailable`. NM activated100,
   `Pi-Fallback`, IPv4 `192.168.50.1/24`; iw xác nhận type AP, SSID RaspPI4OfTT,
   kênh11. HTTP /login nội bộ vẫn200. Windows chủ động WlanScan thành công và
   thấy đúng BSSID của Pi, tín hiệu86%, băng2,4GHz.
4. Timer độc lập đưa Pi về đúng UUID iPhone/IP `172.20.10.5`, phục hồi toàn bộ
   giá trị autoconnect. Báo cáo restore ok, errors=[], checksum file profile
   giống trước thử. Các unit thử tự được systemd collect, không còn timer thử.

Đây là thử **guard kích hoạt AP trên phần cứng và timer recovery**; chưa phải
thử boot ở nơi hoàn toàn không có SSID quen, client thật nhận DHCP, hoặc guard tự
trở về Wi-Fi sau khi hết client. Các nhánh đó có kiểm thử logic, chưa có bằng
chứng phần cứng trong lượt này. Không có tác động robot/GPIO hay restart NM.

Kiểm tra cuối: cả8 source hash live khớp metadata (bỏ installer-units.json sinh
tự động và pycache); các system/user service cần thiết active, không failed unit;
DNS chặn doubleclick.net về0.0.0.0, Cloudflare và Dashboard LAN đều HTTP200;
throttled0x0; không có lỗi kernel USB/I/O/ext4/thiếu nguồn trong boot hiện tại.
Điều này không loại trừ sự cố SSD/USB đã quan sát trên Windows.

Log NM boot mới còn cảnh báo file home-wifi.nmconnection cũ thiếu connection.type;
file đó không được NM nạp. Profile recovery độc lập hợp lệ, profile cũ không bị
ghi đè. Không đủ log trước can thiệp để kết luận nguyên nhân lịch sử duy nhất.

Kit `/opt/pi-control-bootstrap-20261102-network-r1`:

- Archive SHA256 `fc6e03abb1f94fe6148d46a98ab45814022e5fc5df404b1948cefcc52b4ec723`.
- Manifest SHA256 `e88d462881f433f31a405123a5d8593faba7fbd9aa0cc346ac7492b15e484275`.
- `ops/deploy-network-r1.py` **đã chạy**, không chạy lại trên đích hiện có.
- Proofs riêng tư không có mật khẩu tại `ops/reports/fallback-20261102/`:
  live-proof.json, kit.json, baseline-reproduction.txt và windows-ap-scan.txt.
