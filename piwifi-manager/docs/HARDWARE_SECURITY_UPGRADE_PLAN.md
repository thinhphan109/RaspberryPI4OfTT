# Kế hoạch nâng cấp dashboard: nguồn, GPIO, SSH và băng thông

Ngày lập: 14/10/2026. Trạng thái: kế hoạch, chưa triển khai.
Đầu vào: đặc tả người dùng gửi; mã nguồn hiện tại; V31_RELEASE.md và ops/README.md.
Điều chỉnh mới nhất: người dùng yêu cầu tạm bỏ qua quạt. Không triển khai API quạt, PWM, daemon quạt, overlay hay thay đổi đấu nối trong đợt này.

## 1. Hiện trạng đã xác minh và giới hạn

- Backend Flask, frontend vanilla JS/Jinja tại templates/index.html (không phải dashboard.html).
- metrics.py đã đọc nguồn, xung CPU và RX/TX từng interface; observer.py thu thập mỗi 10 giây, snapshot trong /run, ghi SQLite mỗi phút.
- Nguồn đã có bốn cờ hiện tại, nhưng mới có lịch sử bit 16 và 18. operations.js đang hiển thị nguồn/lưu lượng tại tab hoạt động.
- Frontend đã dùng polling 10 giây, sự kiện pi:metrics/pi:view, dừng khi document.hidden; các API phụ chỉ poll ở tab liên quan.
- SQLite hiện tại: writer lâu dài, reader mode=ro, FULL/WAL, retention 7 ngày. Quy tắc 0.4 mới thay thế chính sách này: bản mới ngừng ghi telemetry/events sức khỏe định kỳ xuống SQLite, chuyển lịch sử mới sang RAM. Không xóa DB lịch sử cũ.
- Release nguyên tử, snapshot 5 bản; root-owned symlink /opt/piwifi-web là layout hợp lệ.
- CSS đã có các token của đặc tả; --success ở light là #047857 để giữ tương phản. --font-mono hiện vẫn trỏ Noto Sans: chưa có JetBrains Mono thật.
- Check qua ops/pi.ps1 thất bại vì không phân giải được raspberrypi.local. Chưa audit trực tiếp trạng thái GPIO, kernel, journal hay release đang chạy ngày 14/10. IP các lần trước là dữ liệu lịch sử, không dùng làm IP hiện tại.
- Chưa biết thiết bị nào đang nối GPIO. Điều khiển chân phải tắt mặc định; việc tra cứu và hiển thị trạng thái không phụ thuộc việc mở điều khiển.
- Chưa có Git repository tại workspace; trước sửa mã cần snapshot source có inventory/checksum để giữ mốc so sánh.

## 2. Phạm vi và chỉnh lại đặc tả

Đợt này: nguồn/giảm xung đầy đủ; bảng chân GPIO và trạng thái chỉ đọc; giám sát SSH; biểu đồ băng thông. Điều khiển GPIO được chuẩn bị bằng thiết kế capability/allowlist nhưng chưa kích hoạt trên Pi nếu chưa xác minh đấu nối.

- Frontend mặc định vẫn 10 giây để tiết kiệm tải; có thể chọn 5 giây sau khi đạt ngân sách CPU. Tầng dữ liệu nhanh TTL=0 đọc /proc và /sys trực tiếp khi API cần dữ liệu mới; tốc độ mạng dùng baseline thời gian chia sẻ, không tạo vòng thu thập riêng theo mỗi browser.
- Không sinh dữ liệu mẫu như dữ liệu thật. Thiếu công cụ/quyền: supported=false, reason, timestamp, stale; môi trường demo riêng mới có dữ liệu mẫu với nhãn rõ.
- Không dùng cooling_device0 hay BCM14/18 mặc định; tính năng quạt đã loại khỏi đợt này.
- BCM0/1 (HAT EEPROM), chân nguồn/GND không có thao tác ghi, kể cả xác nhận trên UI.
- Các chân ALT, consumer đang sử dụng hoặc chức năng hệ thống đang bật không được tự chuyển thành output. Allowlist số chân đơn thuần không đủ an toàn.
- Không quảng bá GPIO cấp trực tiếp cho relay, quạt hay servo. UI giải thích mức logic 3,3V, mạch driver và nguồn tải riêng khi cần.
- Không dùng 16mA/500mA như ngân sách dòng bảo đảm cho mọi model; thông số điện phải theo board và tài liệu. Chức năng ALT/PWM cũng cần tách theo model, không sao chép bảng Pi4 cho Pi5.
- Không gọi HIGH là “thiết bị bật”: thiết bị có thể active-low. Nguồn/GND không hiển thị mức điện áp như đã đo nếu không có cảm biến.
- Giao diện SSH dùng “IP có nhiều lần xác thực thất bại”, không kết luận đó là kẻ tấn công chỉ từ bộ đếm.

## 3. Thiết kế thu thập và API

### Nguồn

Mở rộng power_status trong metrics.py, giữ các trường cũ để tương thích UI/MCP. Thêm current_flags, history_flags cho bit 0..3 và 16..19, raw_hex, status, label, supported. Xung CPU tái sử dụng frequency_mhz hiện có; đọc thất bại trả null.

Ưu tiên danger khi có cờ hiện tại, warning khi chỉ có cờ lịch sử, healthy khi raw hợp lệ bằng 0. Lỗi thu thập là unknown, không phải healthy. Nhãn phản ánh đúng cờ, không gán mọi hạ xung là thiếu áp. Lịch sử phần cứng là từ boot, không có thời điểm xảy ra chính xác.

### Lưu lượng

Observer là nguồn duy nhất của mẫu thời gian, không lấy delta theo từng request HTTP. Dùng monotonic cho khoảng đo, lưu mẫu từng interface, phát hiện counter giảm/reset và interface biến mất/tái xuất hiện: mẫu đầu null, không tạo spike/âm.

Chọn interface bằng tuyến mặc định phù hợp; hotspot không có default route vẫn chọn interface AP. Nếu có VPN/Ethernet/Wi-Fi đồng thời, cho biết interface đang xem và giữ dữ liệu từng interface, không cộng trùng lưu lượng tunnel.

API giữ network[] hiện tại; bổ sung primary_interface và boot_id để xác định phiên. RX/TX là byte/giây; UI dùng B/s, KiB/s, MiB/s và GiB đúng phép chia 1024. Tổng là bộ đếm interface trong phiên hoạt động, không khẳng định tổng lifetime hay từ boot nếu interface đã reset.

### SSH

Module security.py riêng: TCP SSH đang established, đăng nhập xác thực thành công, lịch sử và thất bại là các loại dữ liệu khác nhau. who chỉ bao phủ phiên có terminal; ss đếm kết nối, không chứng minh đã đăng nhập thành công. Trả và đặt tên riêng hai loại.

Xác định cổng SSH thực tế; dùng ss không cần -p khi chỉ lấy endpoint. IPv4/IPv6 đều hỗ trợ. last là nguồn phụ: thiếu lệnh/wtmp hoặc dữ liệu không đủ thì báo rõ.

Đọc journal dạng JSON với filter ssh/sshd, tối đa 200 bản ghi mỗi lần và giới hạn byte, timeout=2 giây; không quét toàn bộ 24h. Khởi tạo bằng cửa sổ có giới hạn, sau đó cập nhật theo cursor và loại trùng trong RAM. Nếu tốc độ log vượt 200 bản ghi giữa hai lượt hoặc cursor bị mất, đánh dấu gap/complete=false; không tăng số dòng vô hạn để bù. Phân biệt Failed password/Failed publickey/Accepted, tránh đếm thêm bản ghi PAM trùng một lần xác thực.

Cache SSH 60 giây (có thể 30 giây khi người dùng xem chi tiết), chỉ RAM hoặc tmpfs đã xác minh; /api/security yêu cầu đăng nhập. UI theo server timestamp. Do journald đang volatile theo audit cũ, 24h có thể không đầy đủ sau reboot/rotation: trả coverage_since, complete=false, lý do; không suy ra 0 lỗi khi thiếu quyền/log. Không bật persistent journald chỉ vì tính năng này. Bộ đếm cửa sổ 24h chỉ công bố đầy đủ nếu đã quan sát liên tục đủ thời gian và không có gap; còn lại gọi là số lỗi trong dữ liệu quan sát được.

### GPIO chỉ đọc và điều khiển có điều kiện

Module pinout.py chứa đúng 40 chân vật lý, mapping BCM và mô tả; hardware.py phát hiện board, công cụ, gpiochip/line và consumer. Không cố định gpiochip0 trên Pi5. pinctrl get có thể dùng cho inspection với parser theo fixture thực; raspi-gpio chỉ dùng model phù hợp. Đọc không được chiếm line hay thay direction/pull.

GET /api/gpio/status: timestamp, supported, reason, model, capabilities và trạng thái BCM0..27. Khác biệt giữa trạng thái quan sát được, chức năng có thể cấu hình và capability đang cho phép ghi phải rõ.

Phương án ghi nếu mở ở đợt sau: libgpiod line requests được giữ bởi một dịch vụ phần cứng riêng dưới systemd, không tạo PWM/GPIO thread trong Gunicorn. Mapping và allowlist root-owned; lease/ownership, khóa tuần tự, cấu hình trạng thái khi lỗi/stop được xác định trước cho từng tải. Không tự động phục hồi output HIGH sau reboot. Không dùng pinctrl set để bỏ qua ownership kernel.

POST /api/gpio/control nếu đưa vào bản này phải trả lỗi GPIO_CONTROL_DISABLED khi chưa cấu hình phần cứng. Nếu triển khai controller sau: session+CSRF, schema chặt, chỉ enum/int hợp lệ, không nhận shell/path tùy ý; conflict trả 409, quyền thiếu trả 403, phần cứng không hỗ trợ trả 503. Log thao tác theo thay đổi, không theo polling.

CSRF hiện đọc request.form; mở rộng nhất quán để hỗ trợ JSON/header và giữ tương thích form cũ. Không mở sudo pinctrl/* hay cấp blanket sudo. Tách helper/socket thao tác phần cứng có tập lệnh hữu hạn nếu cần quyền; audit các quyền hiện có của user thinh trước khi bổ sung.

## 4. Giao diện

- Tổng quan: badge nguồn cạnh live, click/keyboard mở chi tiết bốn cờ hiện tại/bốn cờ lịch sử; unknown/stale rõ ràng. Hàng SSH gọn, không đẩy nội dung thành các hộp mới.
- Mạng: bổ sung vùng SVG RX/TX trong bố cục hiện tại, 30 mẫu gần nhất. Nhãn interface/phiên, timestamp; không nối đường qua gap/reboot. sessionStorage có giới hạn, validate dữ liệu và key theo boot/interface; xử lý storage không khả dụng.
- Tổng quan có chỉ số RX/TX nhỏ dùng chung pi:metrics, không thêm request metrics thứ hai.
- GPIO: sơ đồ 2 cột chân lẻ/chẵn, bộ lọc giao thức, inspector và cẩm nang. Màu kèm nhãn, không dùng riêng màu để báo trạng thái. Mobile xếp dọc. Poll status 10 giây chỉ khi tab GPIO đang mở; luôn hiển thị GPIO chỉ đọc nếu chưa mở ghi.
- SSH: bảng năm lần đăng nhập và phạm vi log thực tế; chi tiết đặt tab hoạt động. Cảnh báo tổng quan tái sử dụng snapshot/cache, không thêm quét journal nặng.
- Giữ token/theme và tương phản hiện tại; icon SVG, không CDN. Nếu thêm JetBrains Mono: bundle WOFF2+license vào allowlist deploy, Noto Sans fallback cho tiếng Việt; tabular-nums.
- UTF-8/NFC; kiểm tra dấu tiếng Việt ở light/dark, bàn phím, touch, 390px, reduced-motion. Không sửa title/logo hoặc thiết kế lại toàn dashboard trong đợt này.

## 5. Các giai đoạn thực hiện

1. Khôi phục đường SSH, Check/Audit actual Pi. Ghi model/kernel/tool versions, release checksum, tài nguyên và log coverage; đọc trạng thái GPIO không thay chân. Nếu hostname chưa được thì lấy IP từ router/màn hình, xác minh host key và đúng Pi trước dùng.
2. Tạo snapshot mã nguồn local; triển khai phần đọc nguồn/lưu lượng/SSH/pinout và test fixture trên máy phát triển. Giữ API cũ.
3. Thêm UI tương ứng và kiểm tra browser offline, theme, font, mobile, polling. Đưa endpoint ghi GPIO về disabled mặc định; quạt không nằm trong bundle.
4. Cập nhật inventory trong ops/pi.ps1, syntax list trong deploy.sh, installer, audit, snapshot/restore nếu có file/unit mới. Giữ deploy/network lock, root ownership, cache-busting release và retention cũ.
5. Deploy staging qua workflow có sẵn sau khi preflight đạt, sudo tạm còn hợp lệ; kiểm tra HTTP/login, observer, guard, SSH, dữ liệu cũ và tính năng mới. Không đổi Wi-Fi để test phần cứng.
6. Quan sát 30–60 phút bằng metrics hệ thống và I/O counters; so với baseline mới đo trước deploy. Thử rollback và deploy lại trên chính Pi khi đường phục hồi sẵn, xác nhận lịch sử còn nguyên.
7. Phát hành báo cáo: release/snapshot, tests, sai khác tải/ghi SD, quyền thay đổi và giới hạn thực nghiệm Pi3/Pi5/GPIO vật lý.

## 6. Tiêu chí nghiệm thu

- Power fixtures: 0x0, 0x50000, 0x50005, từng bit, malformed, timeout, thiếu tool. Cờ hiện tại/lịch sử và severity đúng, không hiển thị healthy giả.
- Network fixtures: delta thời gian, reset/reboot, đổi interface, AP không gateway, tunnel, nhiều browser. Client không ảnh hưởng tốc độ đo; 30 điểm không tăng vô hạn.
- SSH fixtures: IPv4/IPv6, nhiều TCP cùng IP, session không TTY, sai password/key, duplicate PAM, thiếu journal/last, reboot/rotation, dữ liệu bị cắt. Coverage và null đúng.
- GPIO: đúng 40 physical, 28 BCM, không trùng mapping; nguồn/GND/0/1 và chân occupied không thể ghi. Chế độ chỉ đọc không claim line. Môi trường không có phần cứng vẫn mở dashboard được.
- Auth/CSRF: GET riêng tư, POST JSON/form thiếu hoặc sai token bị chặn; payload lỗi và injection bị từ chối. Endpoint disabled không tạo hiệu ứng phần cứng.
- Hồi quy toàn bộ test_dashboard.py/test_operations.py, syntax Python/JS/bash, packaging DryRun. Wi-Fi guard, browser ack, rollback và lịch sử cũ không bị hỏng.
- Browser: cả hai theme, offline không request CDN, font Việt, biểu đồ gap/zero/large, không tràn ngang, page hidden dừng poll, không nhân đôi metrics request.
- Hiệu năng: nguồn điện TTL10s, SSH TTL30–60s, GPIO chỉ poll đúng tab; GET định kỳ không ghi SD, không khởi tạo/mutate WAL. CPU tổng process dashboard/observer và các tiến trình con thu thập phải đạt trung bình dưới 1% của toàn Pi trong bài đo ổn định ít nhất 10 phút (đồng thời báo % tương đương một core và số core). Đo cả một browser và nhiều browser; không suy ra đạt khi chưa đo actual Pi. Spike ngắn và tải deploy/test báo riêng.
- Chỉ xác nhận Pi4 nếu thử trên Pi4. Pi3/Pi5 mới là kiến trúc/fixtures cho tới khi có máy thật; outage/boot/hotspot-client vật lý vẫn chưa được coi là đã pass.
- Rollback phải dừng/remove unit mới trước restore, phục hồi enabled/active state và chính sách disabled; không xóa telemetry, cấu hình nhạy cảm hay profile Wi-Fi. Apt/boot config không tự hoàn tác bởi snapshot app: tránh thay trong đợt này hoặc lập rollback riêng.

## 7. Quy tắc 0.4: RAM-only, chi phí thấp và kiểm chứng

Quy tắc người dùng bổ sung ngày 14/10/2026 có ưu tiên cao hơn chính sách lưu lịch sử 3.1 trước đây. Quạt vẫn bị loại khỏi phạm vi.

### Bộ nhớ và vòng thu thập

- Telemetry, cache, cursor SSH, health events mới và lịch sử biểu đồ nằm trong dict/deque giới hạn dung lượng. Lịch sử minute samples có thể giữ tối đa 7 ngày trong RAM nếu ngân sách bộ nhớ cho phép; giới hạn cả số mẫu và byte, dữ liệu chart trả tối đa 360 điểm như API cũ.
- Cần IPC để Gunicorn và MCP đọc chung RAM của observer: snapshot atomic trong /run (xác minh tmpfs bằng findmnt), history RAM ring và endpoint Unix socket chỉ đọc; không lấy “SQLite trên SD làm cache”. Socket có timeout/giới hạn response, owner/mode chặt. Fallback local không sinh tiến trình ghi DB.
- DB cũ giữ nguyên, nếu có đọc thì mode=ro và kiểm chứng không tạo/sửa WAL/SHM; không checkpoint hay migration trong GET. Có thể chọn xem lịch sử cũ một cách chủ động, không đưa vào polling. Không xóa/convert DB trong vòng lặp.
- Restart observer hoặc reboot làm mất lịch sử RAM, cache SSH và thời gian coverage; UI hiển thị rõ “lịch sử từ lần khởi động bộ giám sát”. Deploy/rollback có restart nên cũng có thể làm mất lịch sử mới, DB cũ vẫn còn.
- Theo dõi RAM ring/cache, giới hạn sessionStorage 30 điểm; không lưu bộ đếm mỗi vòng vào file bền vững.
- tmpfs/RAM có thể bị swap xuống SD. Audit cấu hình zram/swap/writeback thực tế trước khi dùng từ “không ghi SD”: cần giữ RAM headroom và tránh swap/writeback trên SD, không tự tắt swap toàn máy. Chưa bảo đảm zero-write toàn hệ thống.

### Phân tầng và subprocess

- Tầng nhanh TTL0: /proc/stat, /proc/meminfo, /proc/net/dev và thermal/cpufreq sysfs, số đọc hữu hạn. Baseline CPU/network dùng monotonic và lock, mẫu không đủ khoảng đo trả null; không làm tăng tần suất sampling theo số tab. Không đưa socket service checks/process scan nặng vào mọi GET.
- Tầng trung bình TTL10s: vcgencmd get_throttled; các kiểm tra khác có cache riêng theo chi phí. Discovery tool/model/path một lần, không chạy command -v từng request.
- Tầng dài TTL30–60s: who/last/journalctl; chỉ một collector chung có lock/single-flight để nhiều request không cùng chạy các lệnh khi cache hết hạn.
- Mọi subprocess mới dùng argv (không shell), timeout=2 giây; timeout/permission/tool missing trả supported/reason/stale, không giả healthy. Không đổi timeout của job đổi Wi-Fi/deploy cũ về 2 giây vì đó là thao tác người dùng và workflow riêng.
- Không coi sysfs read luôn <0,1ms hoặc subprocess luôn tốn một hệ số cố định: đo phân vị latency thực tế, timeout và CPU. Quạt/cooling_device không đọc/ghi trong đợt đã skip.

### Log và ghi bền vững

- Tắt access log cho GET polling hoặc tắt Gunicorn access log và chỉ ghi audit thao tác người dùng. Kiểm tra cả reverse proxy/tunnel, stdout và journald; không log mỗi mẫu/snapshot/health check thành công.
- Lỗi thu thập được throttle/deduplicate vào RAM. Journal hiện có là nguồn đọc; không bật lưu journal/auth.log lên SD để phục vụ dashboard.
- Chỉ POST cấu hình/thao tác thật sự thay đổi mới lưu bền vững theo nhu cầu và audit bảo mật có giới hạn; không ghi lại cấu hình giống hệt. Fan_config không phát sinh vì quạt đã skip.
- Giữ snapshot triển khai và event thao tác quản trị có chủ đích; zero-write polling không cấm deploy, cấu hình hay backup. Phân biệt rõ ghi sysfs điều khiển với ghi filesystem trên SD.

### Visibility và đo nghiệm thu

- document.hidden: clear timer định kỳ metrics/security/GPIO/history, không chỉ gọi callback rồi return. Quay lại trang: fetch một lần, khởi động đúng một timer, tránh burst nhiều request. Không retry vô hạn khi trang bị ẩn.
- GPIO chỉ khi tab gpio visible; SSH dùng cache, không quét log theo từng browser. Observer có thể duy trì history RAM 10s khi không có browser nhưng không poll GPIO; bỏ thu thập process/services quá thường xuyên nếu không cần cho view.
- Kiểm chứng zero-write bằng trace/file inventory và /proc/<pid>/io cho cả app/observer/collector, thêm counter thiết bị SD theo khoảng đo. write_bytes=0 riêng Python không chứng minh mọi child/journald không ghi; I/O hệ điều hành khác báo tách biệt.
- Chạy 10 phút visible, hidden, GPIO và nhiều browser: request counts, CPU process tree, RAM, SD writes. Không đạt <1% thì tối ưu cache/collector trước phát hành, không bỏ dữ liệu lỗi hay gọi kết quả là đạt.
- Rollback tương thích cả backend RAM IPC mới và SQLite cũ; stop/remove unit/socket mới trước restore. Không khẳng định lịch sử RAM được giữ qua rollback.

## 8. Thông tin cần trước deploy

- IP/hostname hiện truy cập được của Pi; sudo chỉ xác thực khi đến bước triển khai, không cần để terminal giữ sudo ngay lúc lập kế hoạch.
- Quạt: đã skip, không chặn tính năng đọc.
- Danh sách thiết bị GPIO: chưa xác nhận, không chặn triển khai pinout/read-only; chặn kích hoạt ghi.

## Nguồn đối chiếu

- [Raspberry Pi hardware/GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).
- [Linux thermal sysfs: type/max_state/cur_state](https://cdn.kernel.org/doc/html/latest/driver-api/thermal/sysfs-api.html).
- [libgpiod request_lines](https://libgpiod.readthedocs.io/en/v2.3/python_misc.html).
- [systemd journalctl: JSON/cursor](https://www.freedesktop.org/software/systemd/man/255/journalctl.html).
- Quy trình local: ops/README.md và piwifi-manager/docs/V31_RELEASE.md.
