# Sao lưu cấu hình Pi có mã hóa

## Dùng hằng ngày

Mở `Pi-Control.cmd`: **Sao lưu Pi có mã hóa**, **Kiểm tra bản sao lưu**, **Xuất khóa phục hồi** và **Mở thư mục sao lưu**. Nếu sudo hết hạn, dùng nút **Cấp quyền sudo tạm** rồi thử lại. Không sửa sudoers và không lưu mật khẩu sudo.

Máy Windows cần Python và `python -m pip install -r ops/backup-requirements.txt`. Khóa AES-256 được tạo ngẫu nhiên, bảo vệ bằng Windows DPAPI CurrentUser. Mỗi bản sao lưu dùng nonce GCM ngẫu nhiên mới. SSH xác minh khóa máy chủ như các công cụ Pi Control khác.

```powershell
.\ops\backup.ps1 -Action Create
.\ops\backup.ps1 -Action Verify
.\ops\backup.ps1 -Action OpenFolder
```

Mặc định lưu `%LOCALAPPDATA%\PiControl\backup\pi-*.picbackup`, ngoài workspace và ngoài thẻ SD. Mỗi lần lưu tạo tệp mới, không tự xóa bản cũ. Chép bản mã hóa sang ổ khác để phòng hỏng ổ Windows. Công cụ hiện chạy theo yêu cầu, chưa đặt lịch tự động vì quyền sudo có thời hạn.

## Phạm vi

Đọc theo danh sách cho phép trong `backup_collect.py`: cấu hình Dashboard, NetworkManager (có mật khẩu Wi-Fi), AdGuard và thông tin đăng nhập, Cloudflare Tunnel, Bluetooth, EasyEffects, WirePlumber, Media, các unit chính và release Dashboard hiện tại. Thống kê ghi SD được chụp nhất quán bằng SQLite online backup trong RAM, không dừng observer. Có manifest SHA-256, quyền/UID/GID gốc, phiên bản gói và kernel. Đường dẫn vắng mặt và symlink bị bỏ qua được ghi vào manifest; không tự dò hoặc đọc toàn bộ ổ.

Không gồm ảnh toàn thẻ SD, Chromium profile/cookie, keyring desktop, khóa SSH cá nhân, dữ liệu Camera, binary AdGuard, log, lịch sử RAM hay toàn bộ snapshot cũ. Cấu hình nhiều dịch vụ được đọc lần lượt, không phải snapshot đồng thời của toàn hệ thống. Giới hạn dữ liệu 128 MiB; lỗi thu thập, giải mã hoặc checksum khiến tác vụ thất bại, không báo thành công giả. Bản sao lưu được giải mã/kiểm tra trong RAM trước khi lưu; nội dung bí mật không ghi vào log hoặc GitHub.

## BẮT BUỘC cho phục hồi trên máy Windows khác

DPAPI mặc định gắn khóa với tài khoản Windows hiện tại. Cần xuất khóa phục hồi được mã hóa bằng mật khẩu riêng **trước khi mất tài khoản hoặc cài lại Windows**:

```powershell
.\ops\backup.ps1 -Action ExportKey -File 'E:\PiRecovery.pickey'
```

Lệnh hỏi mật khẩu hai lần trực tiếp trong terminal (ít nhất 12 ký tự). Nút **Xuất khóa phục hồi** tạo `recovery.pickey` trong thư mục sao lưu; hãy chuyển tệp đó sang nơi cất riêng. Không gửi mật khẩu vào chat, không lưu trong Git. Khóa xuất được mã hóa AES-GCM với Scrypt, salt ngẫu nhiên. Cất khóa và mật khẩu riêng với bản sao lưu. Máy mới nhập khóa trước khi Verify; không ghi đè khóa hiện có:

```powershell
.\ops\backup.ps1 -Action ImportKey -File 'E:\PiRecovery.pickey'
```

## Thử phục hồi, không ghi đè hệ thống đang chạy

```powershell
.\ops\backup.ps1 -Action RestoreFiles -File 'C:\path\pi-example.picbackup' -Destination 'C:\private\pi-restore-new'
```

Thư mục đích phải chưa tồn tại và nên đặt trong thư mục riêng của tài khoản. Lệnh xác minh mã hóa, inventory, đường dẫn và checksum trước khi giải nén; từ chối symlink, đường dẫn tuyệt đối và `..`. Tên thành phần được percent-encode để địa chỉ Bluetooth chứa dấu `:` vẫn giải nén được trên Windows; lấy đường dẫn gốc từ `original_path` trong manifest khi phục hồi lên Linux. Tệp giải nén có chứa bí mật: không đặt trong repo hoặc thư mục chia sẻ. Kiểm tra `manifest.json`, đọc nội dung cần phục hồi cục bộ, rồi xóa thư mục thử khi xong.

Phục hồi lên Pi thật cần chọn đúng cấu hình, cài lại các gói/dịch vụ, phục hồi quyền sở hữu từ manifest và kiểm tra sức khỏe. Với NetworkManager hoặc SSH cần console/Ethernet hoặc đường phục hồi độc lập trước khi thay đổi. Không có nút tự ghi đè toàn bộ Pi: backup này hỗ trợ phục hồi có kiểm soát, chưa được chứng minh là bare-metal recovery. Chưa thử thay thẻ SD hoặc phục hồi toàn máy.

## Kiểm tra GitHub

Workflow `Source checks` chạy trên push/PR và khi bấm Run workflow: cú pháp Python/shell, bộ unittest Linux, biểu đồ/polling JavaScript, kiểm thử mã hóa/phục hồi và Gitleaks toàn lịch sử Git với đầu ra đã che bí mật. Không kết nối hoặc triển khai Pi, không cần mật khẩu Pi. Actions ghim SHA; binary Gitleaks ghim phiên bản và SHA-256. Dependabot chỉ đề nghị cập nhật Actions, không tự merge. Các phiên bản Python dependency vẫn trong dải khai báo, chưa có lockfile tái lập đầy đủ.
