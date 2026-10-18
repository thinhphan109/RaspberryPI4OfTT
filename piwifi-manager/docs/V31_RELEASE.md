# Dashboard 3.1 — giảm ghi SD, deploy và giao diện

Triển khai ngày 12/10/2026, bản đang chạy `/opt/piwifi-releases/20261012T160937-61858`; snapshot trước bản cuối `/var/lib/piwifi-deploy/20261012T160937-61858`.

## Các thay đổi đã triển khai

- Observer giữ một SQLite writer connection suốt vòng đời dịch vụ. Schema/WAL chỉ khởi tạo một lần; web/MCP dùng reader `mode=ro`. Giữ `synchronous=FULL`, ghi mẫu mỗi phút và retention 7 ngày. Checkpoint tự động 256 trang (~1 MiB với trang 4 KiB), bổ sung PASSIVE mỗi 15 phút. SIGTERM đóng connection đúng cách. Không chuyển dữ liệu cấu hình sang RAM hay tăng khoảng dữ liệu chờ commit.
- Cache API lịch sử 30 giây, sự kiện 10 giây, trạng thái mạng 10 giây, deployment 30 giây. Cache trả bản sao và được xóa sau thay đổi Wi-Fi/ack. Frontend chỉ một request metrics mỗi 10 giây, chia sẻ dữ liệu qua event; events/history chỉ ở tab activity, deployment chỉ ở storage, status/progress ở network. Trang ẩn dừng các request định kỳ; quét Wi-Fi chạy theo thao tác người dùng. Progress 3 giây khi chuyển mạng, 30 giây khi không có thao tác; trang đổi mạng dừng poll sau confirmed/recovered.
- `server_time` từ Pi dùng cho tuổi trạng thái guard và thời hạn thông báo. Clamp tuổi tối thiểu 0 và hiển thị “Vừa cập nhật” dưới 5 giây. Không dùng đồng hồ PC để suy ra tuổi dữ liệu Pi. Đồng bộ NTP trên Pi đang đạt.
- Khối phục hồi có khoảng cách, đường phân cách và nút bên phải ở desktop; xếp dọc/nút rộng trên mobile. CSS/JS có query mã release để tránh cache bản cũ khi truy cập qua Cloudflare/tên miền.

## Deploy và rollback

Mã nguồn mỗi phiên bản chuẩn bị trong `/opt/piwifi-releases/<id>`, root-owned. `/opt/piwifi-web` là symlink tới release, root helper/guard và thư viện chia sẻ trỏ gián tiếp qua cùng symlink. Chuẩn bị đầy đủ mã, assets, unit và kiểm tra sudoers trước khi dừng dịch vụ. Chuyển symlink bằng rename, rồi start dịch vụ; có gián đoạn ngắn khi restart, không bảo đảm zero downtime. Lần đầu chuyển thư mục thường sang symlink có một khoảng dừng có kiểm soát.

Deploy và restore đều giữ khóa deploy + network. Snapshot bao gồm symlink và nội dung release được tham chiếu, env root-only, helper/library và unit; dữ liệu observer/events ở ngoài release. Restore runner của các snapshot cũ được cập nhật cho tương thích symlink, archive không thay đổi. Giữ 5 snapshot và tối đa 3 release cache (cộng release đang chạy nếu cần). `scripts/install.sh` chỉ chạy bên trong entrypoint có khóa/snapshot; dùng `ops/pi.ps1 -Action Deploy` từ Windows.

Đã kiểm thử thực tế: triển khai release đầu (migration), triển khai release thứ hai, rollback snapshot chứa symlink về release thứ nhất: HTTP 200, web/observer/guard active, lịch sử còn nguyên. Sau đó deploy bản cuối thêm mã URL assets. Không thử gây lỗi health giả để kích hoạt trap tự phục hồi; restore thực đã được chạy thành công.

## Kết quả kiểm tra

- 33 unittest đạt trên Pi: hồi quy Wi-Fi/guard/auth/CSRF, reader không ghi, cache tránh helper lặp và không chia sẻ mutable data, API có server clock. Syntax Python/JS/bash và allowlist package đạt.
- 40 lượt đọc history/events trên bản đang chạy: `/proc/self/io write_bytes` tăng **0 byte**, so với trước đây 160 KiB cho 5 lượt ở từng reader. Đây là đo process đọc; writer và filesystem vẫn ghi khi lưu mẫu mới.
- DB `quick_check=ok`, còn 292 mẫu tại kiểm tra cuối và tăng bình thường sau các lần restart/rollback; snapshot metrics không stale.
- Browser trên `rasp4.thinhme.tech`: CSS có mã release, restore layout flex đúng; mobile 390px không tràn ngang, font Noto Sans Việt loaded, không lỗi JS từ app. Trong khoảng bắt request khi ở storage chỉ thấy `/api/metrics` và `/api/deployments`, không thấy polling history/events/status ngoài tab.
- Thư mục/archive test tạm đã dọn; không thay NetworkManager profile, env mật khẩu, desktop hoặc tunnel.

## Thảo luận tối ưu toàn Pi

Máy đang boot `graphical.target`, chạy LightDM, labwc, Xwayland, panel/file manager, WayVNC và Raspberry Pi Connect. Nhóm desktop/VNC được đo khoảng **350 MiB PSS**; đây không phải lượng RAM chắc chắn giải phóng khi tắt vì một số thành phần chia sẻ trang/còn phục vụ chức năng khác. `cloudflared`, `htop` đã có. Bluetooth, rpcbind và nfs-blkmap đang active. Chưa thay đổi/tắt các dịch vụ này.

Ưu tiên phù hợp:

1. Nếu Pi chủ yếu dùng SSH/server: cân nhắc boot không desktop và chỉ bật VNC/GUI khi cần. Nếu vẫn thường xuyên dùng desktop thì giữ, tối ưu các app tự khởi động sau khi xác định vai trò.
2. Backup ngoài SD bằng **Restic** tới SSD/NAS/PC hoặc dịch vụ lưu trữ riêng: mã hóa, lưu phiên bản, kiểm tra restore. Cần chọn đích backup trước khi cấu hình; không tự thêm lịch backup chưa có nơi lưu. Cấu hình env/secrets cần bảo vệ trong repository backup.
3. Giữ cloudflared đang dùng; kiểm tra **Cloudflare Access** trước tên miền quản trị để chỉ danh tính được phép truy cập. Không suy ra Access đang tắt chỉ từ trang dashboard mở trong browser đã đăng nhập. Việc này cần truy cập tài khoản Cloudflare và chính sách riêng, chưa thực hiện.
4. **Cockpit** là lựa chọn khi muốn quản trị Linux rộng hơn (journal, dịch vụ, package, storage). Có thể sử dụng bên cạnh dashboard, cần tránh thao tác mạng cùng lúc với guard. Chưa cần cài để tối ưu RAM; đây là tiện ích quản trị tùy chọn.
5. `htop` đã đủ để xem tải. **btop** là tùy chọn giao diện terminal nếu thích biểu đồ rõ hơn. Docker/Podman chỉ cân nhắc khi triển khai nhiều ứng dụng độc lập, vì thêm runtime cũng cần tài nguyên/lưu trữ; hiện systemd đã phục vụ tốt app này.
6. Rà soát NFS/rpcbind, Bluetooth và các đường remote trùng chức năng trước khi tắt. Giữ zram/journald volatile/noatime đã có. Khi mở rộng workload ghi nhiều, ưu tiên SSD USB và nguồn ổn định.

Nguồn chính thức: [Restic](https://restic.net/), [Cockpit](https://cockpit-project.org/), [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/), [btop](https://github.com/aristocratos/btop).
