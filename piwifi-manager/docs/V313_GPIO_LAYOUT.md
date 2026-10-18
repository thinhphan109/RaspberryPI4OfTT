# Dashboard 3.13.1 — sơ đồ GPIO dễ tra cứu

Người dùng yêu cầu nằm ngang, sau đó bác bỏ bản thẻ nhỏ3.13.0 do khó đọc và màu
không rõ. Bản3.13.1 tham khảo cấu trúc trực quan của:
https://raspberry.tips/en/raspberry-pi-gpio-pinout#gpio-detail

Không dùng lại ảnh/mã trang tham khảo. Sơ đồ DOM/CSS riêng, dữ liệu từ APIGPIO
hiện có; không sao chép các khẳng định phần cứng hoặc lệnh điều khiển trên trang đó.

- Header ngang2hàng×20, tên GPIO đặt dọc cỡ15px, số chân13px và nhãn chức năng12px.
  Giữ tên đầy đủ, phân biệt số vật lý và BCM. Cặp chân1/2 ở ngoài cùng bên phải,
  39/40 ngoài cùng bên trái; chân1 có tiếp điểm vuông và hướng dẫn ngay trên hình.
- Tám màu riêng cho3V3/5V/GND/GPIO/I2C/SPI/UART/PWM; tên và tiếp điểm đều có màu.
  Màu theo nhóm tham khảo, không khẳng định chức năng ALT đang được bật.
- PCB chỉ là minh họa trong khung GPIO, màu xanh sẫm; nền toàn Dashboard vẫn đen
  trung tính theo yêu cầu trước. USB/ETH trang trí không phải nút điều khiển.
- Khung chi tiết nằm dưới: màu nhấn theo chân đang chọn, chức năng và INPUT/LOW/
  pull thực tế. SốGPIO/tên/nhóm không thay đổi. GPIO vẫn chỉ đọc, không thêm POST,
  không claim line, không thay cấu hình hay mức điện trên chân.
- Trên màn hình hẹp chỉ sơ đồ cuộn ngang, giữ cỡ chữ và mục tiêu bấm. Bộ lọc vẫn
  hoạt động; giữ focus sau chọn/poll refresh. Không ép40nhãn thành chữ siêu nhỏ.

Release/snapshot cuối: `20261018T175943-317281`.

Kiểm tra production:
- Đủ40chân, mọi cặp có đúng cột/hàng theo số vật lý.
- Chọn chân3 cập nhậtGPIO2/I2CSDA1 và màu xanh; lọcI2C chỉ giữ nổi chân3,5.
- Trình duyệt xác nhận8màu tiếp điểm khác nhau, font tên15px.
- Width390: toàn trang không tràn, vùng sơ đồ rộng1070px có cuộn riêng; chọn được
  chân1 ở đầu phải và40 ở đầu trái, panel chi tiết đổi đúng.
- Width1366/1920: không tràn trang,40chân/8màu/font15px. Viewport được trả mặc định.
- JavaScript syntax qua; các dịch vụ được kiểm tra sau deploy. Chưa kiểm tra
  iPhone thật hoặc đấu dây vật lý; không dùng sơ đồ để xác nhận chân đang trống.
