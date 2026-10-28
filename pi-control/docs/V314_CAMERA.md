# 3.14 — Webcam và timelapse

Đọc [hướng dẫn Camera](../../ops/CAMERA.md).

Thêm camera.py (private IPC client), camera_agent.py (one-reader FFmpeg, RAM
preview, bounded recording/rendering), camera_policy.py (two-region position
gate), pi-camera user unit và một workspace Camera trực tiếp trên dashboard.
Giữ neutral black, các panel chức năng luôn hiện; không thêm nested accordions.

Đóng browser/dời tab dừng preview và polling, không tự dừng phiên đã chủ động ghi.
Khởi động agent không tự mở camera. Preview cùng camera khi timelapse đang ghi.
POST authenticated/CSRF, frame/download authenticated. No public camera ports.

Interval mode dùng 2–60s. Position mode là beta với calibration ảnh mẫu,
hysteresis departure/return, settle window và cooldown. Không phải integration
MQTT và chưa chứng minh chất lượng timelapse trên A1 thực tế.

RAM trial giới hạn riêng; external storage phải là mounted USB whitelist và
không có fallback SD. Ảnh gốc ở ngoài release, có retry rendering khi phiên SSD
bị gián đoạn. Một tác vụ rendering tại một thời điểm, bounded memory/CPU.

Phải giữ các file camera và camera.html/camera.css/camera.js trong allowlist,
installer, AST checks, user-unit snapshot/rollback. CI cần Pillow và FFmpeg cho
test render thật; Ubuntu runner có FFmpeg, Pi được installer kiểm tra.

## Kết quả triển khai 2026-10-24

Release và snapshot: `20261024T072344-131326`.
143 Python checks passed; existing Node chart, polling, Nonstop checks passed.
Shell syntax verified on normalized LF payload. Actual webcam: staging recorded
50 frames and rendered MP4 while preview stayed live. Production authenticated
HTTP smoke test recorded 4 frames/6 seconds, verified JPEG/no-store, CSRF,
missing-calibration rejection, unsafe storage rejection, MP4 download and
camera off/on. Pi web/observer/Wi-Fi guard/AdGuard/Media active after deploy.
8-second sample of agent+FFmpeg: 14.14% of one CPU core. Not long-run telemetry.
Camera layout measured at390/1366px: no document horizontal overflow.
No actual A1 Smooth phase/layer verification yet. SSD was not connected;
mount removal exercised in test doubles only. No physical iPhone/reboot test.
