# Dashboard 3.3 và Pi Control

Triển khai ngày 15/10/2026. Release cuối `/opt/piwifi-releases/20261015T114924-15820`.
Snapshot phục hồi trước release cuối `/var/lib/piwifi-deploy/20261015T114924-15820`.
Snapshot `/var/lib/piwifi-deploy/20261015T114652-14814` phục hồi về bản trước tính năng 3.3.
Retention tiếp tục 5 snapshot; snapshot chứa cấu hình Pi-hole và có thể chứa secrets,
chỉ root truy cập trên Pi, không xuất ra Windows.

## Sử dụng

- Dashboard: https://rasp4.thinhme.tech/#apps, đăng nhập như trước.
- Mục Ứng dụng và Truy cập hiển thị IP LAN, Wi-Fi, thời điểm đọc, nút sao chép IP,
  đường dẫn dashboard/Pi-hole và tình trạng 3 dịch vụ. EdgeVision chỉ bind loopback;
  không mở thêm cổng Internet hoặc LAN cho camera.
- Trên iPhone cùng mạng với Pi: mở mục này, sao chép IP vào cấu hình DNS Wi-Fi.
  Bấm Kiểm tra DNS để thử một tên miền ngẫu nhiên rồi đối chiếu trong RAM Pi-hole.
  Kết quả nhận được truy vấn chứng minh đường DNS đã tới Pi-hole; không chứng minh
  mọi ứng dụng đều dùng cùng DNS. Không nhận được truy vấn chỉ là chưa xác định,
  có thể do cache, VPN, Private Relay hoặc trình duyệt chặn yêu cầu thử.
- Quảng cáo YouTube không phải phép thử hoạt động DNS và không được bảo đảm chặn.
- Windows: mở shortcut Pi Control trên Desktop hoặc Pi-Control.cmd tại thư mục gốc.
  Tự tìm qua raspberrypi.local, tiếp đến IP cache và IP LAN cũ; mọi ứng viên đều phải
  qua SSH StrictHostKeyChecking với host key raspberrypi.local. Không quét subnet.
  Nếu không tìm được, lấy IP từ dashboard qua tên miền và nhập thủ công.
- 14 nút: tìm Pi, sao chép IP, mở tên miền, mở dashboard LAN, mở Pi-hole,
  camera qua SSH tunnel, trạng thái hệ thống, sudo tạm, sao chép mật khẩu Pi-hole,
  kiểm tra DNS, bật DNS, cập nhật DNS, khôi phục DNS, mở SSH.
- Camera tunnel cục bộ 127.0.0.1:18767 tới 127.0.0.1:18766 trên Pi; giữ terminal mở.
- Sudo vẫn nhập trực tiếp qua terminal. Chỉ thay đổi DNS Windows mới yêu cầu UAC.
  Không lưu sudo password hoặc thêm quyền NOPASSWD. Mật khẩu Pi-hole chỉ đọc qua
  SSH vào clipboard khi bấm nút; không trả về dashboard công khai.

## Quy trình khi đổi mạng

1. Pi kết nối Wi-Fi đã lưu hoặc dùng hotspot dự phòng để cấu hình lần đầu.
2. Khi NetworkManager báo up/down/dhcp4-change trên wlan0, dispatcher gọi tác vụ
   root độc lập để cập nhật listener DNS và ACL web Pi-hole theo IP/subnet mới.
3. Windows mở Pi Control và chọn Cập nhật DNS theo IP Pi. UAC vẫn cần nếu thay DNS;
   bản sao DNS gốc được giữ, không bị ghi đè qua mỗi lần cập nhật.
4. iPhone sửa DNS Wi-Fi sang IP hiển thị. iOS không được điều khiển từ xa tự động.
5. Nếu Pi offline, nút Khôi phục DNS cũ trên Windows vẫn hoạt động không cần SSH.

Không có Tailscale trong luồng mới. Cài đặt Tailscale cũ và listener của nó được giữ
nguyên theo yêu cầu tạm bỏ qua. Cloudflare Tunnel cũ không bị thay đổi.
Tên miền dashboard giúp tìm IP mới khi Pi có Internet; nó không chuyên chở DNS53.
IP LAN khác mạng không truy cập được từ 4G/5G bằng cách này.

## Cơ chế và phạm vi

Danh mục apps.json dùng chung cho dashboard và Windows. API /api/hub yêu cầu
đăng nhập, cache RAM15s, giao diện chỉ poll30s khi mục apps đang hiển thị và không
poll khi ẩn. Có trạng thái dữ liệu cũ khi lỗi. Không truy cập SQLite lịch sử mới.
Phép thử DNS tạo challenge trong cookie session có chữ ký, hết hạn60s, giới hạn
tạo mỗi10s. Chỉ trả việc nhìn thấy domain challenge, không trả IP client, lịch sử
duyệt web hoặc SID/mật khẩu API Pi-hole. API nội bộ dùng localhost bỏ qua proxy.
Giữ queryLogging=false, maxDBdays=0, DHCP/NTP tắt và lịch sử RAM như trước.

Sync root không sửa Wi-Fi hoặc DHCP. Chỉ nhận cấu hình Pi-hole đã quản lý
listeningMode NONE và bind-dynamic; gặp directive lạ sẽ từ chối ghi đè.
Không chiếm DNS192.168.50.1 của AP. ACL quản trị Pi-hole cho phép subnet Wi-Fi hiện
tại với mật khẩu Pi-hole; đây là mở rộng từ một IP Windows để dùng các thiết bị
của người dùng trong LAN. DNS không được publish qua Cloudflare. Giới hạn cho
thiết bị cụ thể cần quy tắc firewall/ACL bổ sung nếu sau này có yêu cầu.
Không có ghi định kỳ cho đồng bộ: chỉ ghi cấu hình khi địa chỉ hoặc ACL thực sự
đổi; cùng IP là no-op. Thao tác quản trị/deploy và Pi-hole khác vẫn có thể ghi đĩa.

## Kiểm chứng và giới hạn

- 50 unittest Linux đạt, gồm auth/CSRF, session DNS, expiry, IP/URL mới, no-op,
  IP mới thay IP cũ, không chiếm AP DNS, phục hồi bytes khi dnsmasq-test thất bại.
- JS syntax và polling lifecycle đạt. PowerShell5.1 parse và Pi Control dựng đủ
  14 nút; trạng thái qua SSH và DNS UDP/TCP từ Windows đạt.
- Production browser qua Cloudflare: danh mục và IP chính xác; phép thử DNS nhận
  được challenge. Mobile390px không tràn ngang; đã trả viewport về mặc định.
- Live API smoke: chưa query -> query khớp, probe chặn đạt, ba ứng dụng active.
  Mẫu20s GET hub: process web write_bytes delta0. Sync cùng IP không đổi mtime.
  Không phải bảo đảm toàn host zero-write hoặc kiểm thử tải lớn.
- Lần deploy đầu sync chờ restart FTL15s quá ngắn, trap tự phục hồi bản3.2 và
  DNS. Đã sửa chờ systemctl120s; deploy tiếp theo đạt, bản cuối sync no-op đạt.
- Chưa thử thay Wi-Fi thực, boot/outage/AP client hoặc iPhone vật lý trong đợt
  này. Chưa tự bấm UAC/DNS mutation trên Windows vì cấu hình đang dùng được;
  cần người dùng bấm nút khi muốn thay DNS.

## Phục hồi

ops/pi.ps1 -Action Rollback dùng snapshot gần nhất. Muốn về bản trước tính năng
3.3, root chạy restore.sh trong snapshot20261015T114652-14814 khi snapshot còn
được giữ. Runner snapshot mới cũng phục hồi cấu hình Pi-hole, dispatcher và
symlink helper, rồi khởi động lại Pi-hole. Không gỡ packages dùng chung.
