# Pi Media — Dashboard 3.6

Mở <https://rasp4.thinhme.tech/#media> và đăng nhập bằng tài khoản Dashboard.
Nếu vừa đăng nhập từ liên kết sâu mà bị về Tổng quan, chọn **Media · Điều khiển
nhạc** ở thanh điều hướng.

1. Bấm **Mở cửa sổ Media** nếu chưa kết nối. Pi cần có phiên desktop của `thinh`.
2. Dán link một video YouTube/YouTube Music, bấm **Phát ngay** hoặc **+ Hàng đợi**.
3. Dùng Phát/Tạm dừng, tua ±10 giây, âm lượng video và Bài tiếp. Âm thanh phát
   tại Pi qua đường PipeWire/EasyEffects, không truyền về điện thoại.
4. Hàng đợi tối đa 50 video, tự chuyển khi video kết thúc. Dùng nút Bỏ hoặc Xoá
   hàng đợi. Hàng đợi và trạng thái điều khiển nằm trong RAM, mất khi agent restart.

## Nghe tự động và chặn quảng cáo

### Nonstop (đã bật)

Nút **Nonstop đang bật · Tắt** trên Media điều khiển watchdog trong agent,
không phụ thuộc việc điện thoại giữ trang Dashboard mở. Cứ 3 giây khi bật:
giữ Autoplay, thử phát lại nếu video bị tạm dừng và chỉ xác nhận hộp thoại
“Video paused / Continue watching / Tiếp tục xem” được nhận diện. Không tự
điền mật khẩu, đăng nhập, đồng ý điều khoản hoặc xử lý CAPTCHA.

Nếu video hết và YouTube chưa chuyển, Nonstop dùng link Bài tiếp do player
cung cấp. Nếu phát kẹt 180 giây, báo lỗi hoặc mất cửa sổ, thử mở/khôi phục video.
Các lần phục hồi lỗi chờ60,120,240… tối đa900giây để tránh tải lại liên tục.
Không tải lại chỉ vì đang phát quảng cáo. Mất điện/Internet, keyring, tài khoản,
video không khả dụng vẫn có thể làm dừng; không bảo đảm phát vô hạn.

**Tạm dừng trên Dashboard luôn ưu tiên:** watchdog không phát lại cho tới khi
bấm Phát, chọn video khác hoặc bật lại Nonstop. Tạm dừng trực tiếp trong cửa sổ
YouTube có thể được Nonstop coi là gián đoạn và tự phát lại; dùng Dashboard
hoặc tắt Nonstop khi muốn dừng chủ động.

Lựa chọn bật/tắt, tạm dừng chủ động, video gốc và volume lưu trong file0600
`~/.local/state/pi-media/nonstop.json`, chỉ ghi khi thao tác rõ ràng từ người dùng.
Theo dõi vị trí, đếm lỗi và video tiếp theo trong RAM; không ghi tiến độ định kỳ.
Restart agent giữ lựa chọn Nonstop, nhưng có thể phục hồi về video gốc đã lưu;
queue và vị trí gần nhất vẫn không bền qua reboot. Cần phiên desktop/keyring sẵn sàng.

Kiểm chứng:64Python tests và5Node scenarios về nhận diện hộp thoại/thông báo đăng
nhập đạt; chạy thật trên video hiện tại, manual pause qua hơn1chu kỳ watchdog
rồi resume đạt; configmtime không đổi trong10giây polling. Chưa chờ giới hạn
inactivity nhiều giờ hoặc gây mất mạng/tắt điện thật để thử phục hồi.

Không cần xếp hàng đợi: chọn một video ban đầu, bật Autoplay trên YouTube trong
cửa sổ Media. Khi không có hàng đợi riêng, YouTube tự chọn video liên quan.
Dashboard hiển thị “YouTube tự đề xuất” khi đọc được công tắc đang bật.
YouTube có thể tạm dừng sau thời gian dài không tương tác; không cam kết phát vô hạn.

uBlock Origin Lite chính thức có ID `ddkjiahejlhfcafbddmgiahcphecmpfh`.
Runner `ops/install-media-ubol.py` tạo chính sách cài/cập nhật từ Chrome Web Store
và mức Optimal tại `/etc/chromium/policies/managed/pi-media-ubol.json`.
Chính sách áp dụng các profile Chromium trên Pi, không ảnh hưởng Windows.
Bản trước/restore root-only ở `/var/lib/pi-media-setup/<timestamp>/restore.sh`.
Dashboard rollback không gỡ chính sách này; dùng restore riêng nếu cần.
Browser Media phải cho phép extension và background networking để tự cập nhật.
AdGuard DNS tiếp tục chạy; uBOL bổ sung lọc nội dung ngay trong trình duyệt.
Khả năng chặn YouTube có thể thay đổi; không bảo đảm hết mọi quảng cáo.

Ngày 18/10: xác nhận uBOL2026.1012.1545 trong profile Media, from_webstore=true,
location7 (external policy download), disable_reasons trống; managed Optimal.
Video và vị trí nghe được khôi phục sau restart, Autoplay=true, hàng đợi trống.
Không ép nhấn thông báo “vẫn đang xem” hoặc cam kết bỏ qua giới hạn inactivity.

Trang hiển thị tên, ảnh bìa, tiến độ, trạng thái phát và dấu hiệu quảng cáo.
Tìm kiếm hiện mở YouTube trên điện thoại; sao chép link video và gửi về Media.
Chưa có tìm kiếm tích hợp, playlist yêu thích, hẹn giờ hoặc chuyển preset EQ.

## Cửa sổ riêng và đăng nhập

Media điều khiển một cửa sổ Chromium riêng tại
`~/.local/share/pi-media/chromium`. Không tiếp quản hoặc đóng các tab trình duyệt
cũ. Nếu hai cửa sổ đều phát nhạc, tạm dừng cửa sổ cũ trực tiếp trên Pi.

Lần đầu, hệ thống có thể hỏi mật khẩu keyring trên desktop và chặn trang tải.
Chủ máy tự nhập/tạo mật khẩu trực tiếp trên Pi; không gửi mật khẩu qua chat hoặc
Dashboard. Không vô hiệu hoá kho mật khẩu hoặc kiểm tra chứng chỉ. Đăng nhập
YouTube trong cửa sổ Media nếu cần tài khoản; phiên đăng nhập tách khỏi Chromium cũ.

Nút Raspberry Pi Connect là liên kết tới công cụ remote desktop của Raspberry Pi;
không phải stream màn hình tích hợp và không tự cấu hình/tạo tài khoản Connect.

## Vận hành

User services: `pi-media.service` (agent, enabled) và `pi-media-browser.service`
(cửa sổ chỉ mở theo yêu cầu). Đóng cửa sổ Media thì bấm Mở lại trên Dashboard.
Mã root-owned theo `/opt/piwifi-web`; cấu hình user units ở `/etc/systemd/user`.
Deploy bằng `ops/pi.ps1 -Action Deploy`; rollback snapshot bao gồm user units.
Rollback trước 3.6 dừng/retire agent và browser; profile Chromium vẫn được giữ.

Browser debugging chỉ bind `127.0.0.1:18769`, không public hoặc đưa qua tunnel.
Agent dùng Unix socket `/run/user/1000/pi-media.sock` mode0600. Dashboard giữ
authentication/CSRF; API chỉ nhận các lệnh định sẵn và link HTTPS video YouTube
chuẩn hoá, không có endpoint chạy shell hoặc JavaScript tuỳ ý. Người có cùng
tài khoản Linux vẫn có thể truy cập browser debug; không dùng profile này cho
công việc nhạy cảm khác.

Dashboard chỉ polling khi mục Media đang hiển thị; agent kiểm tra kết thúc khi
có hàng đợi. Không ghi lịch sử polling. Chromium vẫn có cache/cookie ghi đĩa
thông thường; không tuyên bố cả hệ thống không ghi thẻ nhớ.

YouTube có thể chặn tự phát, yêu cầu đăng nhập/xác minh hoặc thay đổi giao diện.
Thông báo cần thao tác trực tiếp xử lý trên desktop. Các link playlist bị rút về
một video để giảm xung đột với hàng đợi riêng; chế độ autoplay YouTube vẫn có thể
ảnh hưởng chuyển bài. Live stream không có thời lượng cố định và chỉ chuyển khi
luồng thực sự kết thúc hoặc bấm Bài tiếp.

## Kiểm chứng 18/10/2026

57 kiểm thử Linux đạt; API HTTP thật kiểm tra đăng nhập, CSRF, hàng đợi và từ
chối link ngoài YouTube đạt. Đã phát video thử, đọc tên/thời lượng, chỉnh âm lượng,
tạm dừng/phát, tua và tự chuyển hàng đợi khi kết thúc. Preview bố cục desktop và
390px không tràn ngang. Có lỗi keyring ở lần đầu/khởi động lại browser, chủ máy
đã tự xử lý; phiên cuối quan sát được video đang phát. Không vô hiệu hoá keyring.

Đã thêm hook giữ âm lượng qua navigation với CDP session sống lâu; cơ chế session
có kiểm thử, nhưng lần xác minh chuyển-video sau sửa cuối chưa hoàn tất vì chủ máy
đã chọn nội dung mới và phiên đó được giữ nguyên. Chưa thử reboot hoặc thao tác
từ iPhone thật. Connect chỉ là liên kết; chia sẻ màn hình chưa được kiểm chứng.
# Upcoming video and volume schedule (3.7)

Live deployment18October2026:release20261018T114852-257541, recovery snapshot
`/var/lib/piwifi-deploy/20261018T114852-257541` (root only, latest five retained).
72Python tests,5Node prompt tests and polling lifecycle passed. Live cap20%,
request100% remained20%, disabling retained20%,10speriodic configuration mtime
unchanged. Restored user's100%volume,Nonstop on,disabled22:00–07:00/30%preset.
Dashboard next title and settings save verified through the existing signed-in
browser. Actual overnight boundary, reboot and long unattended run remain pending.

Open Media to view the actual YouTube next recommendation. **Bỏ qua bài này**
moves to that recommendation (or the first RAM queue entry). Suggestions may
change before the current video ends. Titles are read from YouTube's metadata.

Expand **Giới hạn âm lượng theo giờ**, enable it, set start/end and the maximum
video volume, then **Lưu giới hạn**. Prepared defaults:22:00–07:00,30%,disabled.
Time is fixed to Vietnam UTC+7 regardless of the controlling phone timezone.
The cap works with Nonstop off and never raises volume when the window ends.
It controls only the dedicated Media player; other desktop audio is unaffected.
The watchdog checks every3seconds; it is not a hardware sound pressure limiter.

# Local dislikes, sleep and repeat protection (3.8)

Deployed18October2026:release`20261018T121211-261691`; root-only recovery snapshot
`/var/lib/piwifi-deploy/20261018T121211-261691` (five retained).88Python tests,
5Node prompt checks and polling lifecycle passed. Live dislike/skip/undo and
recent-video exclusion exercised; actual one-minute fade, expiry with Nonstop on
and agent-restart stop latch exercised. Physical reboot/overnight remain pending.

- **Không thích bài này** records the video locally and advances to an eligible
  recommendation. If none exists, it pauses. Expand **Chống lặp & Bài không thích**
  and **Bỏ chặn** to undo. It does not submit a dislike to YouTube.
- **Hẹn giờ ngủ** accepts1–720minutes (default input30). Volume fades in the last
  2minutes, then playback stays paused even with Nonstop on. **Hủy hẹn giờ** cancels
  an active timer without raising volume. After expiry, **Phát** resumes and restores
  starting volume within the scheduled cap.
- **Chống lặp** starts enabled for3hours; configure1–24hours or turn it off. It uses
  exact video IDs and500RAM transitions; history resets when Media restarts. Explicit
  **Phát ngay** can replay a recent video, but dislikes require **Bỏ chặn** first.

