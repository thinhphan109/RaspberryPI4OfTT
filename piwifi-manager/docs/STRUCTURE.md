# Giải thích cấu trúc Linux của Pi Wi-Fi Manager

## `/opt/piwifi-web`

`/opt` thường dành cho phần mềm bổ sung do quản trị viên cài ngoài bộ package chuẩn của distro. Mã Flask và template HTML được đặt ở đây để tách khỏi file hệ điều hành.

## `/usr/local/sbin/piwifi-helper`

`/usr/local` dành cho file do quản trị viên tự cài và không thuộc package manager. `sbin` phù hợp với lệnh quản trị hệ thống. Helper thay đổi NetworkManager nên đặt ở đây, root sở hữu.

## `/etc/piwifi-web.env`

`/etc` chứa cấu hình toàn hệ thống. File này giữ thông tin cấu hình runtime: tài khoản Web UI và secret của Flask. Không đặt secret trực tiếp trong source.

## `/etc/sudoers.d/piwifi-web`

Một file riêng trong `sudoers.d` cho phép user chạy đúng helper bằng sudo không cần nhập password. Tách file riêng giúp dễ kiểm tra/xóa mà không sửa trực tiếp `/etc/sudoers`.

## `/etc/systemd/system/piwifi-web.service`

Service do quản trị viên tự tạo đặt tại đây. systemd dùng file này để khởi động Gunicorn tự động sau NetworkManager và restart nếu process lỗi.

## Vì sao Web app không chạy root?

Web server xử lý input từ trình duyệt nên không nên có toàn quyền root. Flask/Gunicorn chạy bằng user thường. Chỉ thao tác mạng cần quyền cao được chuyển sang helper nhỏ có API lệnh giới hạn.

## Luồng quyền

```text
Browser (không đặc quyền)
   |
Flask/Gunicorn - user thinh
   |
sudo chỉ cho piwifi-helper
   |
piwifi-helper - root
   |
nmcli -> NetworkManager
```

Đây là nguyên tắc least privilege: thành phần nào cần quyền gì thì chỉ cấp đúng quyền đó.
