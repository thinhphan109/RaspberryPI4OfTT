# Khôi phục lịch sử cập nhật — 28/10/2026

Các commit trước `29b1b81` được giữ nguyên. Những commit bổ sung được tạo khi
đồng bộ lại dự án; chúng không phải commit Git gốc đã tồn tại trên Pi.

- `AuthorDate` của bản ghi lịch sử lấy từ thời điểm deploy trong nhật ký,
  hiển thị theo giờ Việt Nam. `CommitDate` là thời điểm khôi phục lịch sử.
- Nhóm `docs(history)` ghi lại release 24–26/10 từ ghi chú và lịch sử deploy SD.
  Không còn snapshot mã nguồn riêng cho từng release này trong bộ dữ liệu đang
  truy cập. Những commit đó chỉ bổ sung hồ sơ release, không giả làm source
  snapshot của thời điểm đó. Ghi chú được giữ ở trạng thái khi khôi phục và có
  thể chứa các nhận xét bổ sung sau ngày phát hành.
- Nhóm `feat(history)`/`fix(history)` khôi phục payload mã nguồn từng module
  27–28/10 từ bundle bất biến đã đối chiếu manifest và checksum. Chỉ dùng
  release có trong nhật ký deploy, không đưa bản thử chưa cài vào lịch sử.
- Payload được ghép tại đường dẫn ứng dụng cũ `piwifi-manager/` trong các
  checkpoint khôi phục; commit đồng bộ sau cùng chuyển về `pi-control/`.
  Đường dẫn runtime trên Pi không bị thay đổi bởi thao tác Git này.
- Binary AdGuard và dữ liệu runtime không đưa vào Git. Bộ cài lấy binary từ
  nguồn chính thức có checksum; archive build, credentials, cookie, video,
  log chẩn đoán và bản sao lưu riêng tiếp tục bị loại khỏi repository.
- Đây là các checkpoint khôi phục có nguồn gốc xác định. Tài liệu, kiểm thử và
  tooling hiện hành được đồng bộ ở phần cuối; không coi mọi commit trung gian
  là một bản phát hành độc lập đã được chạy lại toàn bộ kiểm thử.

Nguồn đối chiếu:

- `ops/migration/deploy-history-legacy-sd-20261027T060547Z.json`
- `ops/migration/deploy-history-modular-20261028.json`
- `docs/RECOVERED_HISTORY.json`: từng sự kiện, loại bằng chứng, release và
  checksum manifest của bundle dùng để khôi phục.

Ngày push lên GitHub là ngày đồng bộ thực tế. Không thay đổi thời gian push,
không sửa commit cũ và không dùng force push.
