# HƯỚNG DẪN SỬ DỤNG ESP32 MANAGER TOOL (v1.7)

> **Cập nhật theo phiên bản:** `v1.7` (Giao diện thuần PyQt6 — Phong cách Kỹ thuật Chuyên sâu)

---

## MỤC LỤC
1. [Giao diện Tổng quan & Thanh Trạng Thái Hợp Nhất](#1-giao-dien-tong-quan--thanh-trang-thai-hop-nhat)
2. [Tab 1: Kiểm tra Chip & Phần cứng](#2-tab-1-kiem-tra-chip--phan-cung)
3. [Tab 2: Serial Monitor & Bảng Điều Khiển IoT](#3-tab-2-serial-monitor--bang-dieu-khien-iot)
4. [Tab 3: Nạp Firmware (.bin)](#4-tab-3-nap-firmware-bin)
5. [Tab 4: Phân vùng Bộ nhớ (Partition Wizard)](#5-tab-4-phan-vung-bo-nho-partition-wizard)
6. [Tab 5: Sao lưu & Nhân bản Đa Mạch](#6-tab-5-sao-luu--nhan-ban-da-mach)
7. [Tab 6: Cài đặt & Cập nhật](#7-tab-6-cai-dat--cap-nhat)

---

## 1. GIAO DIỆN TỔNG QUAN & THANH TRẠNG THÁI HỢP NHẤT

- **Sidebar bên trái:** Thu gọn / mở rộng nhanh để chuyển giữa 6 trang làm việc chính (`Kiểm tra Chip`, `Serial Monitor`, `Nạp Firmware`, `Phân vùng`, `Sao lưu & Chép`, `Cài đặt`).
- **Thanh kết nối chung phía trên:** Chọn **Cổng COM**, **Baudrate**, làm mới danh sách cổng hoặc bấm **Kết nối** / **Ngắt kết nối** Serial bất cứ lúc nào.
- **Thanh tiến trình hợp nhất ở đáy màn hình:**
  - Hiển thị trạng thái kết nối Serial, tên tiến trình đang thực thi ở bên trái thanh tiến trình, thanh tiến trình (0% -> 100%) và tỷ lệ `%` ở bên phải.
  - Phục vụ chung cho cả Tab 1 (Kiểm tra Chip), Tab 3 (Nạp Firmware / Xóa Flash), Tab 4 (Đọc / Nạp / Dump / Ghi / Xóa phân vùng) và Tab 5 (Đọc cấu trúc / Sao lưu / Nhân bản).

---

## 2. TAB 1: KIỂM TRA CHIP & PHẦN CỨNG

### Mục đích
Đọc nhanh cấu hình phần cứng thực tế từ chip Espressif (Chip Model, Revision, Crystal, Tính năng Wi-Fi/BLE, Flash JEDEC, PSRAM, các vùng Heap RAM và MAC Address/OUI).

### Thao tác thực hiện
1. Cắm mạch ESP32 vào máy tính và chọn cổng COM ở thanh phía trên.
2. Nhấn **Kiểm tra Chip** (tiến trình chạy hiển thị ở thanh trạng thái đáy).
3. Nếu muốn theo dõi log thô từ `esptool`, tích chọn **Xem log thô esptool**.
4. Bấm **Báo cáo Liền mạch** để đọc báo cáo văn bản hoặc **Bảng Thông số** để xem dạng bảng có bộ lọc tìm nhanh.
5. Nhấn **Lưu Báo Cáo** để xuất thành file `.txt`.

---

## 3. TAB 2: SERIAL MONITOR & BẢNG ĐIỀU KHIỂN IOT

### Theo dõi & Gửi dữ liệu UART
1. Chọn cổng COM và tốc độ Baudrate phù hợp (mặc định `115200`), nhấn **Kết nối**.
2. Dữ liệu phản hồi từ ESP32 xuất hiện theo thời gian thực; hỗ trợ **Tự động cuộn** và **Thêm dấu thời gian**.
3. Nhập lệnh vào ô phía dưới, nhấn `Enter` hoặc nút **Gửi** (tùy chọn **Thêm \r\n**; dùng phím Mũi tên Lên/Xuống để duyệt lại lịch sử lệnh).
4. Bấm **Reset ESP** để khởi động lại mạch qua tín hiệu DTR/RTS hoặc **Ẩn / Hiện Bảng Điều Khiển** khi cần mở rộng Terminal.

### Bảng điều khiển Mạng & 15 Phím F1 - F15
- **Cấu hình Mạng (Wi-Fi & Server):** Cho phép gửi nhanh lệnh quét Wi-Fi, kết nối Wi-Fi và nối TCP Server về thiết bị ESP đang chạy firmware tương thích.
- **Phím F1 - F15:** Gửi nhanh các chuỗi lệnh cấu hình sẵn hoặc tùy chỉnh trong `Cài đặt -> Phím chức năng F1 - F15`.

---

## 4. TAB 3: NẠP FIRMWARE (.BIN)

### Nạp nhiều file firmware đồng thời
1. Chọn dòng **Chip** (`auto`, `esp32`, `esp32s3`, `esp32p4`,...) và **Baud** (`460800`, `921600`,...).
2. Trong card cấu hình trên cùng đã tích hợp đủ 4 nút điều khiển gọn trên một hàng: **Bắt đầu nạp**, **Xóa vùng nhớ**, **Xóa toàn bộ Flash** và **Xóa nhật ký**.
3. Tích chọn từ 1 đến 4 dòng tệp `.bin` (hỗ trợ nút **Chọn...** hoặc kéo thả file `.bin` vào từng ô đường dẫn), nhập **Offset (Hex)** tương ứng (`0x0`, `0x1000`, `0x8000`, `0xe000`, `0x10000`,...).
4. Bấm **Bắt đầu nạp**. Ứng dụng kiểm tra chống chồng lấn dải địa chỉ và hiển thị tiến trình phần trăm trên thanh trạng thái đáy.

### Công cụ Xóa Flash
- **Xóa vùng nhớ:** Mở hộp thoại chỉ định địa chỉ bắt đầu và dung lượng cần xóa (tự kiểm tra căn lề 4 KB).
- **Xóa toàn bộ Flash:** Xóa trắng toàn bộ bộ nhớ SPI Flash.

---

## 5. TAB 4: PHÂN VÙNG BỘ NHỚ (PARTITION WIZARD)

- **Khởi tạo sạch:** Bảng phân vùng và sơ đồ ổ đĩa luôn trống khi mới mở cho đến khi bạn chọn **Mẫu Chuẩn...**, **Quét Dự Án**, **Mở CSV/BIN**, **Đọc bảng từ Chip**, hoặc bấm **+ Thêm dòng**.
- **Tự đặt Flash cao nhất theo dòng Chip:** Khi chọn dòng chip ở danh sách **Chip**, ứng dụng tự động lọc dung lượng tương thích và chọn dung lượng **Flash cao nhất** mà dòng chip đó hỗ trợ.
- **Thêm phân vùng ngay sau dòng đang chọn:** Bấm **+ Thêm dòng** (hoặc nhấp dòng `+` cuối bảng) để chèn phân vùng mới ngay phía sau dòng đang được chọn trên bảng, đồng thời tự động tránh trùng tên.
- **Lưu CSV toàn bảng:** Bấm **Lưu CSV** để lưu toàn bộ bảng phân vùng hiện có ra tệp `.csv` chuẩn ESP-IDF (tự lưu đè nếu đang mở tệp `.csv`, hoặc mở hộp thoại chọn vị trí lưu lần đầu).
- Chi tiết xem thêm tại [HUONG_DAN_PHAN_VUNG.md](HUONG_DAN_PHAN_VUNG.md).

---

## 6. TAB 5: SAO LƯU & NHÂN BẢN ĐA MẠCH

- **Khởi tạo sạch & Đọc Chip Nguồn:** Danh sách phân vùng và sơ đồ đĩa ban đầu trống; chọn **Board Gốc** và bấm **Đọc Cấu Trúc Từ Chip Nguồn** để tải toàn bộ bố cục Flash (kể cả `bootloader` và `partition_table`).
- **Tùy chọn ẩn Nháy LED 5 giây nhận diện Board Gốc:**
  - Mặc định tắt để giữ gọn giao diện; có thể bật trong **Cài đặt -> Cài đặt Chung và Cổng COM -> Tùy chọn ẩn (Tab 5 - Sao lưu & Nhân bản)**.
  - Khi đã bật và đang ở trong **Tab 5**, chọn cổng **Board Gốc** sẽ tự động nháy LED TX trong 5 giây (qua luồng UART TX không xung DTR/RTS) để dễ nhận biết board đang cắm trên máy tính; nút **Nháy LED** cũng xuất hiện ngay bên cạnh ô `Board Gốc`.
  - Việc nháy LED tự động dừng ngay khi hết 5 giây, khi chuyển khỏi Tab 5, hoặc khi chạy thao tác phần cứng.
- **Sao lưu & Hồ sơ xác thực:** Tích chọn các phân vùng cần sao lưu (bật/tắt **Cắt trống 0xFF** tùy chọn), bấm **Sao lưu vùng chọn** hoặc **Sao lưu Toàn bộ Flash** để lưu tệp `.bin` kèm `backup_info.txt`, `backup_manifest.json` (chứa SHA-256 & MD5) và `partitions.csv`.
- **Sao Chép Trực Tiếp Đa Mạch:** Chọn nguồn (Board Gốc trực tiếp hoặc Thư mục đã lưu), tích chọn các **Board Đích**, rồi bấm **Bắt đầu Sao Chép Đa Mạch**.

---

## 7. TAB 6: CÀI ĐẶT & CẬP NHẬT

1. **Cài đặt Chung và Cổng COM:**
   - Chọn chế độ **Giao diện Kỹ thuật**: **Giao diện Tối (Dark)** hoặc **Giao diện Sáng (Light)** áp dụng tức thì không cần khởi động lại.
   - Cấu hình **Quản lý cổng COM** (quét định kỳ 2 giây, tự ưu tiên cổng mới cắm, lọc Bluetooth, ẩn danh sách cổng COM chỉ định) và **Tùy chọn ẩn nháy LED 5s (Tab 5)**.
   - Cấu hình **IP Server** & **Cổng TCP** mặc định.
   - Xem thông tin phiên bản `v1.7`, tác giả, giấy phép GPL-3.0 và bấm **Kiểm Tra Cập Nhật** từ GitHub Releases.
2. **Phím chức năng F1 - F15:** Tùy biến nhãn hiển thị và chuỗi lệnh UART gửi đi cho 15 phím điều khiển.
3. **Khôi phục gốc / Lưu Cài Đặt:** Áp dụng thay đổi và lưu xuống tệp cấu hình cục bộ.
