# Đề xuất chuyển OS sang SSD và tách các thành phần Pi Control

Ngày: 27/10/2026. Đã chốt hướng cài sạch SSD; kiến trúc và cách thực hiện đang thảo luận.
Phạm vi cập nhật: SSD đã ghi OS, chuẩn bị layout offline và deploy đủ 8 module;
xem `ops/ssd_bootstrap/STATUS_20261027.md` và `ops/ssd_bootstrap/README.md` để biết
bằng chứng, giới hạn và cách cập nhật tiếp. SD/EEPROM không bị đổi.

## Mục tiêu

Cài sạch OS trên SSD 128 GB, cấu hình mới và quản lý từng thành phần
độc lập. Cài lại máy từ cấu hình khai báo được; cập nhật Dashboard không làm
gián đoạn Wi-Fi, DNS, Camera hoặc phiên Media. Giao diện quản lý vẫn gọn.

## Lựa chọn mới của chủ máy

- Cài mới hoàn toàn trên SSD 128 GB hiện có; format/ghi OS và layout SSD đã hoàn tất.
- Không clone hoặc backup hệ thống/cấu hình/dữ liệu cũ. Source trên Windows
  được dùng để tái triển khai; chỉ mang lịch sử deploy sang.
- Phân vùng đã áp dụng theo layout được giao thiết kế. SD và ổ Windows khác không bị sửa.
- Quản lý service phải có Trợ giúp giải thích cụ thể từng unit.
- SMART mới: Percentage Used31%, Critical Warning0, Spare100%, MediaErrors0,
  ErrorLogEntries7274 không đổi, nhiệt độ51°C. Chưa chứng minh tải dài hạn.

## Bản cũ trước khi chuyển SSD

Hồ sơ deploy gần nhất: 4.2.0, release `20261026T103747-20600`.
Đã vào Pi trực tiếp qua192.168.1.30, giữ xác minh host key raspberrypi.local;
mDNS chưa phân giải trên Windows. Root là /dev/mmcblk0p2 ext4, dùng14GB/59GB,
boot512MiB; RAM3,7GiB, available khoảng3,1GiB tại mẫu idle, throttled0x0.
Lúc khảo sát Pi chưa nhận SSD/webcam qua USB; đây là baseline cũ. SSD sau đó được
nhận diện, SMART và USB3 kiểm tra; chi tiết trạng thái mới ở biên bản deployment.

Các service NetworkManager, web/observer, AdGuard, cloudflared, tailscaled,
Bluetooth, PipeWire/WirePlumber, EasyEffects và Raspberry Pi Connect đang hoạt
động. Guard chạy oneshot theo timer; inactive giữa hai lượt là bình thường.
EdgeVisionRobot cũng đang active tại /home/thinh/edgevision-robot/current,
unit user edgevision-robot.service, thuộc dự án riêng; active chưa chứng minh
webcam đang có mặt hoặc mô phỏng là điều khiển phần cứng thật.

| Thành phần | Cấu trúc hiện tại | Điểm cần cải tiến |
|---|---|---|
| Dashboard | piwifi-web.service | Tên và đường dẫn còn gắn với dự án Wi-Fi ban đầu |
| Wi-Fi fallback | piwifi-guard.service + timer, NetworkManager | Đã là service riêng; bộ cài chưa tự dựng đầy đủ profile Pi-Fallback |
| Quan sát | piwifi-observer.service | Thu thập riêng nhưng source/release chung với Dashboard |
| Media | pi-media.service + pi-media-browser.service | Agent và browser riêng; Audio/Bluetooth nằm trong agent Media |
| Camera | pi-camera.service | Ghi hình và luồng ghép video thuộc cùng agent |
| DNS, tunnel | adguardhome, cloudflared | Đã tách runtime; cần hợp nhất khai báo cài đặt/phục hồi |
| Deploy | một release /opt/piwifi-web | Bộ cài dừng web/observer/guard và restart Media/Camera cùng đợt |

Đổi tên unit đơn thuần chưa giải quyết việc deploy chung. Cần tách cả source,
dependency, cấu hình, dữ liệu, quyền truy cập và quy trình cập nhật.

## Chọn cách chuyển OS

| Phương án | Dữ liệu/phần mềm hiện có | Ưu điểm | Chi phí và giới hạn |
|---|---|---|---|
| Clone SD sang SSD | Giữ OS, gói, cấu hình và phần lớn trạng thái bền trên SD | Chuyển nhanh, ít thay đổi hành vi | Giữ cả cấu hình cũ; vẫn phải refactor sau đó; cần clone nhất quán và kiểm tra boot/UUID |
| Cài sạch SSD và deploy mới (đã chọn) | OS/gói/cấu hình mới, chỉ nhập lịch sử deploy | Chuẩn hoá bộ cài và dễ cài lại | Cần cấu hình và đăng nhập lại các thành phần |

Lựa chọn đã xác nhận: cài sạch SSD và deploy lại từ source Windows, cấu hình
mới; không phục hồi cấu hình hệ thống cũ. Bảng trên lưu các phương án tham khảo,
lựa chọn mới thay thế khuyến nghị phục hồi có chọn lọc trước đây.

Pi 4 hỗ trợ boot USB khi bootloader/BOOT_ORDER phù hợp. Kiểm tra cấu hình thực
tế trước khi đổi; không áp dụng hướng dẫn OTP dành cho Pi đời cũ. Raspberry Pi
Imager ghi image sẽ ghi đè dữ liệu trên thiết bị đích.

Nguồn chính thức: [USB mass storage boot](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#usb-mass-storage-boot),
[cài OS bằng Imager](https://www.raspberrypi.com/documentation/computers/getting-started.html#install-an-os).

SSD từng có lỗi NTFS. Chủ máy đã chọn xoá và cài lại, không yêu cầu giữ dữ liệu cũ. Lần ngắt USB 14:09:25 ngày 25/10 đã được xác nhận là chủ
động rút ổ; nguyên nhân hai lần 03:06/11:07 vẫn chưa xác định. Trước khi dùng
làm ổ OS cần kiểm tra SMART mới và độ ổn định nguồn/cáp/bridge dưới tải. Không
coi việc đổi filesystem là đã xử lý nguyên nhân mất kết nối USB.

## Hệ điều hành và layout đã áp dụng

Đề xuất Raspberry Pi OS 64-bit bản Desktop cơ bản để tiếp tục dùng Chromium,
Spotify/YouTube, PipeWire, Bluetooth và EasyEffects trong phiên desktop.
Media cần phiên đồ hoạ; Camera, mạng, DNS, observer và Dashboard cần hoạt động
được độc lập với phiên desktop.

Với SSD thực tế119,2GiB, layout đã áp dụng: bootFAT32 512MiB; rootext4 40GiB;
dataext4 68GiB tại /srv/pi-control; khoảng10,7GiB chưa phân vùng. Root cũ dùng
14GB nên40GiB có khoảng phát triển. Vùng chưa phân vùng không làm
sức khoẻ trở lại100%; hiệu quả thu hồi NAND còn phụ thuộc TRIM qua bridge.
Không mặc định TRIM/UAS/USB3 đã hoạt động chỉ từ tên JMicron. Đây là layout dự kiến, không phải layout
mặc định sau khi Imager tự mở rộng root. Tách phân vùng dữ liệu giúp giới hạn
việc video chiếm đầy root; hai phân vùng cùng SSD vẫn chung rủi ro phần cứng.

| Đường dẫn đề xuất | Nội dung | Thiết lập/duy trì |
|---|---|---|
| /opt/pi-control/<module>/releases + current | Code và phiên bản từng module, root quản lý | Deploy/rollback đúng module |
| /etc/pi-control/<module> | Cấu hình, bí mật theo quyền riêng | Khai báo/cấu hình mới theo module |
| /var/lib/pi-control/<module> | Trạng thái bền, job, thống kê | Schema có version; không tự tạo backup |
| /run/pi-control/<module> | Socket, cache, telemetry tạm | Tự tạo khi khởi động |
| /srv/pi-control/camera | Ảnh gốc, video, manifest | Backup dữ liệu riêng, retention theo chính sách |

Dữ liệu lớn và cấu hình bí mật không đặt trong release/Git. Theo lựa chọn mới,
không bật module backup hoặc lập bản sao hệ thống. Hệ quả: mất SSD có thể mất
ảnh/video mới; khả năng cài lại source không thay thế việc khôi phục dữ liệu.

## Ranh giới module và service đề xuất

Giữ một repository với module rõ ràng và systemd phù hợp Pi 4. Các thành phần
nhẹ có thể chung observer; worker ghép video chỉ chạy khi có việc.

| Module | Unit chính dự kiến | Trách nhiệm và ranh giới |
|---|---|---|
| Dashboard | pi-control-dashboard.service | UI, đăng nhập, API tổng hợp; gọi agent/helper qua giao diện cố định |
| Network | pi-control-network-guard.service + timer | Fallback/reconnect qua NetworkManager, hoạt động cả khi web dừng; helper giới hạn thao tác mạng |
| Observer | pi-control-observer.service | Tài nguyên, sức khoẻ, nhật ký chọn lọc và thống kê ổ; không điều khiển player/camera |
| Media | pi-control-media.service | Điều khiển nguồn phát, sleep, lịch âm lượng, queue/chính sách phù hợp từng nguồn |
| Media browser | pi-control-media-browser.service | Chromium/profile; chỉ chạy khi sử dụng; tách vòng đời khỏi web |
| Audio | pi-control-audio.service trong phiên desktop | PipeWire/WirePlumber, Bluetooth, định tuyến và âm lượng; chạy được khi Media nghỉ |
| Camera | pi-control-camera.service | Sở hữu webcam, preview, ghi ảnh và phiên; không phụ thuộc desktop |
| Render | pi-control-camera-render@.service | Ghép job đã đóng, giới hạn CPU/RAM/I/O, không chiếm webcam |
| DNS | adguardhome.service | AdGuard, cấu hình riêng; cập nhật Dashboard không restart DNS |
| Remote | cloudflared.service | Truy cập ngoài mạng; lỗi tunnel không làm mất Dashboard qua LAN |
| Deploy history | module lịch sử trong Dashboard/Observer | Import lịch sử SD cũ và ghi deploy mới; không tạo daemon backup |
| EdgeVision Robot | edgevision-robot.service, quản lý từ registry | Giữ dự án và bộ deploy riêng; Dashboard chỉ đăng ký quản lý/trợ giúp |

Tailscale không nằm trong danh sách cài mới mặc định theo lựa chọn trước đây.
Bản đang chạy trên SD không bị thay đổi.

NetworkManager, ssh, bluetooth, PipeWire/WirePlumber và EasyEffects vẫn là
phần mềm nền với vòng đời riêng. Chỉ cài/bật module được chọn. Tên unit là đề
xuất; cần kế hoạch chuyển đổi để không còn hai guard cùng điều khiển Wi-Fi.

Dashboard vẫn mở được nếu một agent hỏng và hiển thị thành phần đó không sẵn
sàng. Không tạo phụ thuộc Requires từ web vào toàn bộ dịch vụ. Quan hệ phụ
thuộc chỉ khai báo khi thật sự cần: network guard cần NetworkManager, Media
browser/Audio cần desktop và PipeWire, render cần bộ ảnh/đích lưu hợp lệ.

Agent có tài khoản/quyền thiết bị phù hợp, socket riêng và API có version.
Hành động đặc quyền đi qua helper có danh sách cho phép, không cho nhập shell
tuỳ ý. Không hardcode tài khoản thinh, UID1000, IP LAN hoặc UUID ổ vào module.

## Bộ cài và quản lý cấu hình

Một cấu hình máy khai báo module bật/tắt, nơi lưu, hạn mức, tên người dùng
desktop và chính sách mạng. Bộ cài áp dụng lặp lại an toàn, kiểm tra dependency
và tình trạng trước/sau. Pi Control trên Windows tiếp tục là điểm gọi tác vụ.

Mỗi module có install, configure, verify, update, rollback và export/restore.
Update web chỉ restart web; update Media chỉ restart agent nếu browser không
cần đổi; update Camera kiểm tra recording trước. Render đang chạy không chặn
deploy web. Migration dữ liệu có version; rollback code không tự hạ schema hoặc
ghi đè dữ liệu mới. Các API tương thích phải được kiểm tra trước khi chuyển.

Bộ cài phải dựng được mạng/SSH/DNS/ứng dụng từ máy sạch. Không đưa cấu hình cũ
vào OS mới mặc định; các thông tin đăng nhập/cấu hình ngoài cần khai báo lại
khi cài module tương ứng. Khoá/mật khẩu không đưa vào repository hoặc log.
Bản backup mã hoá cũ, nếu đã tồn tại, không bị đọc/khôi phục/xoá trong bước này.

## Các điều chỉnh chức năng cần làm cùng migration

1. Nhận diện ổ OS và ổ dữ liệu theo thiết bị/UUID, thay mmcblk0 cố định trong
   thống kê ghi SD. Lịch sử SD cũ giữ định danh riêng; không gán sang SSD và
   không coi số byte ghi là tuổi thọ NAND còn lại.
2. Camera dùng storage policy mới. UUID/phân vùng cũ sẽ thay khi ghi image;
   nếu root nằm trên USB thì cơ chế hiện chỉ chọn USB mount ngoài không thể
   phục hồi nguyên xi. Cần xác minh mount, quota và dung lượng dự phòng; đích
   dữ liệu vắng mặt thì từ chối ghi, không rơi sang root/SD.
3. Tách capture/render, lưu trạng thái job theo sự kiện để nhận diện phiên
   gián đoạn, ghép lại ảnh hợp lệ, tải ảnh/video và dọn dữ liệu có chính sách.
   Không tự xoá ảnh quan trọng hoặc báo ghép thành công khi chưa đủ khung.
4. Chuẩn hoá health theo module: phiên bản, trạng thái, lý do suy giảm, CPU/RAM,
   hành động có thể dùng và log liên quan. Lỗi lặp được gộp, sự kiện phục hồi
   tách rõ; bảo toàn chính sách retention và ghi gộp hiện có.
5. Network bootstrap phải tạo được fallback từ máy sạch. Kiểm thử mất Wi-Fi,
   AP có client, trở về mạng đã lưu, thay IP và khởi động không có Internet.
   Tạo đường phục hồi độc lập trước các thao tác có thể cắt mạng.
6. Spotify Free/DRM/quảng cáo và Camera Position vẫn có phần chưa kiểm chứng
   thực tế. Hiển thị rõ khả năng đã có và giới hạn; dùng kiểm thử thật trước
   khi nâng trạng thái tính năng. GPIO giữ chế độ chỉ đọc đang được cho phép.
7. Rà lại log2ram sau khi OS lên SSD: cân bằng RAM, khả năng giữ log và lượng
   ghi. Chốt chính sách trước khi đổi; telemetry hiện vẫn ở RAM, nhật ký/thống
   kê bền chỉ theo các ngoại lệ đã được yêu cầu.

Giao diện đề xuất có năm nhóm: Tổng quan, Mạng & DNS, Media & Âm thanh, Camera,
Hệ thống. Trung tâm service nằm trong Hệ thống; bộ lọc nhật ký liên kết tới
module. Tách kỹ thuật không bắt buộc tăng số mục điều hướng hoặc giấu chức
năng thường dùng vào nhiều tầng xổ xuống.

## Quản lý service và Trợ giúp

Mỗi module có manifest dùng chung cho installer, Dashboard và log: mã module,
tên tiếng Việt, unit thực tế, scope system/user, cách kích hoạt, dependency,
quyền thao tác, đường dẫn cấu hình/dữ liệu và nội dung Trợ giúp. Không tự đọc
nội dung env hoặc nhận tên unit bất kỳ từ browser để chạy lệnh đặc quyền.

Mỗi dòng service có nút Trợ giúp gồm:

- Dùng cho chức năng nào, ứng dụng nào sở hữu và có cần desktop/Internet không.
- Chạy liên tục, theo lịch hay khi có nhu cầu; khi nào inactive là bình thường.
- Tác động của dừng/restart; thao tác nào có thể cắt mạng, DNS hoặc phiên ghi.
- Cách xử lý lỗi thường gặp và đường dẫn mở nhật ký đã lọc đúng module.

Ví dụ guard hiển thị “Chờ lượt kiểm tra mạng” nếu timer active và lượt trước
thành công; không báo đỏ chỉ vì oneshot đang inactive. Unit not-found do alias
PipeWire/Connect không được đưa vào danh sách lỗi ứng dụng. Phân biệt service
active với khả năng thật: thiếu webcam, chưa đăng nhập Spotify, lỗi tunnel.
Chức năng điều khiển vẫn hiển thị trực tiếp; Trợ giúp chỉ chứa giải thích.

Camera và EdgeVision cần cơ chế phân quyền sở hữu webcam: một ứng dụng giữ
thiết bị tại một thời điểm, ứng dụng khác nhận trạng thái bận rõ ràng. Không
mặc định cho hai FFmpeg/agent cùng mở thiết bị. Luồng dùng chung có thể bàn sau.

## SD cũ và tuổi thọ SSD

Đề xuất dùng SD làm thẻ cứu hộ có OS Lite, SSH và công cụ chẩn đoán ổ/mạng;
khởi động thủ công để sửa/kiểm tra SSD hoặc cài lại. Sau khi SSD boot và nghiệm
thu xong mới xử lý SD. Không format SD trong phạm vi cho phép format SSD.
Khi thử bootSSD độc lập rútSD để xác nhận đúng nơi boot. Thẻ cứu hộ không tự
đồng bộ dữ liệu, không tự động chuyển OS khi SSD lỗi và không thay thế backup.

Đọc được báo cáo cũ C:/Program Files/CrystalDiskInfo/DiskInfo.txt, mtime21/10:
PM991 NVMe Samsung128GB, sức khoẻ69%, PercentageUsed31%, CriticalWarning0,
AvailableSpare100%, MediaAndDataIntegrityErrors0, ErrorInformationLogEntries7274,
PowerOnHours9488, nhiệt34°C. Đây là số liệu cũ, không phải SMART ngày27/10.
Windows CIM từ chối quyền đọc reliabilitycounter hiện tại. Không kết luận ổ
đã hỏng chỉ từ số ErrorLog, cũng không tuyên bố an toàn24/7 từ sức khoẻ69%.
Cần đọc SMART/errorlog mới và kiểm tra kết nối trước khi dùng làm OS.

Giảm ghi: telemetry và cache tạm ở RAM có giới hạn, zram, profile/cookie bền
trên SSD, log chọn lọc ghi gộp, Camera bật theo nhu cầu và retention rõ ràng.
Chỉ áp dụng TRIM định kỳ sau khi xác minh bridge hỗ trợ; không benchmark ghi
liên tục chỉ để chứng minh tốc độ. Format không đặt lại mức hao mòn NAND.

Nguồn: [NVMe Percentage Used là ước lượng mức đã dùng](https://www.intel.com/content/www/us/en/support/articles/000056960/technologies/memory-and-storage/ssd-management-tools.html),
[CrystalDiskInfo Health Status](https://crystalmark.info/en/software/crystaldiskinfo/crystaldiskinfo-health-status/).

## Lịch sử deploy mang sang

Đã xuất metadata riêng, không phải backup OS/cấu hình:
`ops/migration/deploy-history-legacy-sd-20261027T060547Z.json`, kèm .sha256.
Có67sự kiện kind=deploy hiện còn trong events.json và thông tin release4.2.0,
releaseid/sourcehash/thời điểm. Không mang snapshot khôi phục root chứa bí mật,
profile trình duyệt hoặc các log mạng khác.

Schema pi-control.deploy-history/v1; mỗi record có event_id ổn định, nhãn
legacy-sd/legacy-bundle/historical_only, rollback_available=false. Khi import
vào SSD cần kiểm tra checksum/schema, giới hạn trường và dedupeevent_id; không
coi release cũ là bản đang cài trên OS mới. Giữ timestamp gốc; deploy mới nhận
os_generation riêng. Registry/log hiển thị “Hệ thống SD cũ” và “Hệ thống SSD”.
Không hứa lịch sử đầy đủ từ trước đến nay: chỉ xuất những sự kiện còn lưu.

## Trình tự chuyển đổi

1. Hoàn thiện và kiểm thử bộ cài theo module ở Windows; xác nhận registry và
   Trợ giúp. Giữ source trên Windows để dựng lại máy.
2. Đọc SMART mới, xác nhận đúng SSD128GB và kiểm tra nguồn/cáp/bridge; chuẩn
   bị lịch sử deploy cuối trước khi tắt hệ thống SD. Không tạo backup OS.
3. Cài mới SSD bằng image chính thức, chuẩn bị layout đã chọn; không để lần
   mở rộng root đầu tiên chiếm phần dự kiến dành cho data. Chưa format SD.
4. BootSSD độc lập, kiểm tra root/boot/mount đúng ổ; cấu hình SSH/Wi-Fi mới.
   Xác minh host key mới; đặt Windows DNS về chế độ có thể truy cập mạng trong
   lúc Pi DNS chưa sẵn sàng, bật lại watcher sau khi SSH/DNS đã kiểm chứng.
5. Deploy Network/fallback và Dashboard/Observer/DNS; tiếp đến Audio/Media,
   Camera/Render, EdgeVision và Remote theo manifest. Nhập lại cấu hình cần
   thiết, không phục hồi hệ thống cũ. Import lịch sử deploy với nhãn SD cũ.
6. Thử reboot/offline/fallback, update web khi Camera hoạt động, Audio khi
   Media nghỉ và tải đồng thời. Sau đó thảo luận vai trò SD; chưa chọn thẻ cứu hộ.

## Tiêu chí nghiệm thu

- SSD boot được độc lập, không phát sinh USB reset/I/O lỗi trong bài thử tải.
- Web dừng hoặc deploy không làm mất Wi-Fi fallback, DNS hoặc phiên Camera.
- Media nghỉ không làm mất Audio/Bluetooth và không đóng phiên desktop.
- Render giới hạn tài nguyên và không làm cạn dung lượng dành cho OS.
- Mạng mất/khôi phục, boot offline và AP có client được thử trên thiết bị thật.
- API/log/health chỉ ra đúng thành phần lỗi, polling không phát sinh ghi bền.
- Module cài lại được từ bộ cài; lịch sử deploy import đúng, không trùng hoặc
  gán release cũ thành hiện tại. Nếu chọn thẻ cứu hộ, cần thử boot riêng.

## Cần chốt trước triển khai

Hướng cài sạch SSD128GB, không backup và chỉ chuyển lịch sử deploy đã hoàn thành.
Layout512MiBboot/40GiBroot/68GiBdata/~10.7GiBfree được áp dụng. Registry/Help và
8 module đã deploy trên generation mới; SSH, DNS và Dashboard login đã kiểm tra.
Vai trò SD vẫn chưa quyết định; thẻ cũ giữ nguyên. Còn bài thử dài USB/nguồn,
reboot, fallback, Audio/Bluetooth, Spotify, Camera dài hạn và iPhone.
