# TÀI LIỆU KIẾN TRÚC HỆ THỐNG - ESP32 MANAGER TOOL (v1.1)

Tài liệu chi tiết về kiến trúc phần mềm, mô hình phân lớp, thiết kế đa luồng và các nguyên lý cốt lõi của **Esp32 manager tool**.

---

## 1. TỔNG QUAN KIẾN TRÚC (HIGH-LEVEL ARCHITECTURE)

Ứng dụng được xây dựng theo mô hình **Component-based Mixin Architecture** kết hợp giao diện đồ họa **Tkinter/ttk**, sử dụng **esptool** và **PySerial** làm engine phần cứng cấp thấp.

```
+-------------------------------------------------------------------------+
|                                main.py                                  |
|   - Thiết lập High-DPI Per-Monitor V2 & AppUserModelID Win32            |
|   - Multiprocessing freeze support & Khởi chạy ứng dụng                 |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                  modules/app_core.py (InspectorApp)                     |
|                   Bộ điều khiển trung tâm & Vòng đời                     |
+-------------------------------------------------------------------------+
       |                  |                  |                  |
       v                  v                  v                  v
+--------------+   +--------------+   +--------------+   +--------------+
| TabInspector |   |  TabMonitor  |   |  TabFlasher  |   | TabPartition |
|   (Tab 1)    |   |   (Tab 2)    |   |   (Tab 3)    |   |   (Tab 4)    |
+--------------+   +--------------+   +--------------+   +--------------+
       |                  |                  |                  |
       +------------------+------------------+------------------+
                                  |
       +--------------------------+--------------------------+
       |                          |                          |
       v                          v                          v
+---------------+        +------------------+       +------------------+
|  esptool_util |        |   serial_util    |       | modules/partition|
|  & stream_util|        |  (PySerial COM)  |       |   (Model, Spec,  |
+---------------+        +------------------+       |  BIN Compiler)   |
       |                          |                 +------------------+
       v                          v                          |
+----------------------------------------------------+       |
|                  ESP32 / ESP8266                   |<------+
|               Phần cứng qua cổng COM               |
+----------------------------------------------------+
```

---

## 2. PHÂN TÍCH CÁC MODULE CHÍNH

### 2.1. Lớp Điều Khiển Trung Tâm (Core Application)
- **`main.py`**: Điểm khởi động ứng dụng. Gọi Windows API (`ctypes`) để bật chế độ Per-Monitor V2 DPI Awareness và AppUserModelID độc lập nhằm đảm bảo giao diện sắc nét trên mọi tỷ lệ màn hình (100% đến 200%).
- **`modules/app_core.py`**: Chứa lớp `InspectorApp` kế thừa các Mixin chức năng (`InspectorTabMixin`, `MonitorTabMixin`, `FlasherTabMixin`, `PartitionTabMixin`, `SettingsDialogMixin`).
  - Quản lý trạng thái chia sẻ (cổng COM hiện hành, baudrate, giao diện Sáng/Tối).
  - Điều phối vòng đời ứng dụng, các cờ luồng (`is_detecting`, `is_flashing`, `stop_serial_thread`).
  - Đảm bảo an toàn khi thoát (`on_closing`), đóng cổng Serial và giải phóng tài nguyên.
- **`modules/config.py`**: Hằng số hệ thống, bảng màu (`DARK_PALETTE`, `LIGHT_PALETTE`), dải Baudrate, cấu hình phím điều khiển F1–F15 và đường dẫn file cấu hình JSON người dùng.

### 2.2. Lớp Tương Tác Phần Cứng & Luồng (Hardware & Stream Utilities)
- **`modules/esptool_util.py`**:
  - Wrapper đa luồng an toàn thực thi các lệnh `esptool` mà không gây đóng băng (freeze) giao diện người dùng Tkinter.
  - Xử lý các lệnh: đọc thông tin chip (`chip_id`, `flash_id`), đọc MAC, nạp flash (`write_flash`), xóa flash (`erase_flash`, `erase_region`), đọc phân vùng (`read_flash`).
- **`modules/stream_util.py`**:
  - Đón bắt luồng `stdout`/`stderr`, lọc bỏ mã thoát màu ANSI (ANSI Escape Codes), giải mã ký tự UTF-8 gia tăng (`incrementaldecoder`) và chèn mốc thời gian (timestamp).
- **`modules/serial_util.py`**:
  - Quét và liệt kê cổng COM của hệ thống qua PySerial, tự động lọc và ưu tiên các vi mạch cầu nạp thông dụng (CH340, CP210x, FTDI, ESP JTAG).
- **`modules/mac_database.py`**:
  - Cơ sở dữ liệu tĩnh chứa 335 mã tiền tố OUI được IEEE cấp cho Espressif Systems.
  - Hỗ trợ đối soát và suy luận địa chỉ MAC Wi-Fi Station, Wi-Fi AP và Bluetooth từ Base MAC.
- **`modules/binary_scanner.py`**:
  - Kiểm tra tính toàn vẹn của file firmware `.bin` (Magic byte `0xE9`, SPI mode, Flash size, target chip).
  - Hỗ trợ quét thư mục dự án và phân tích file manifest cấu hình.
- **`modules/update_util.py`**:
  - Kết nối GitHub Releases API (`ybao2004/esp32_manager_tool`) để kiểm tra phiên bản mới theo chuẩn semantic version.
  - Tải trực tiếp bản cập nhật qua HTTP Stream với callback thanh tiến trình thời gian thực.
- **`modules/win32_util.py`**:
  - Nhúng icon đa độ phân giải trực tiếp vào Handle cửa sổ Windows (`WM_SETICON`) để tránh vỡ hạt icon.

### 2.3. Lớp Quản Lý Phân Vùng (Partition Engine - `modules/partition/`)
- **`partition_model.py`**:
  - Định nghĩa thực thể `PartitionEntry` và `PartitionTable`.
  - Phân tích và tạo file định dạng `partitions.csv` chuẩn ESP-IDF.
  - Biên dịch trực tiếp cấu trúc nhị phân 32-byte (`struct.pack`) kèm mã băm MD5 Checksum (Magic `0xAA50`, Subtype, Offset, Size, Flags).
  - Thuật toán `auto_pack()`: Dồn biên tự động và căn lề 64 KB (`0x10000`) cho App, 4 KB (`0x1000`) cho Data.
  - Bộ kiểm tra tính hợp lệ toàn diện (`validate()`): Kiểm tra trùng lặp tên, độ dài tên, địa chỉ offset tối thiểu, thiếu otadata, vượt dung lượng flash.
- **`chip_database.py`**:
  - Bảng thông số phần cứng của toàn bộ các dòng vi điều khiển Espressif (dung lượng Flash tối đa, offset mặc định của bootloader và partition table).
- **`unit_formatter.py`**:
  - Chuyển đổi linh hoạt giữa các định dạng: số nguyên thập phân, Hexadecimal, chuỗi dung lượng (`64K`, `1M`, `4MB`), tính toán số Sector 4 KB.
- **`project_scanner.py`**:
  - Quét tự động thư mục dự án ESP-IDF / PlatformIO để tìm file `partitions.csv` và các file `.bin` đã biên dịch trong thư mục `build/`.

### 2.4. Lớp Hộp Thoại & Giao Diện Người Dùng (Tabs & Dialogs)
- **`modules/tabs/`**:
  - `tab_inspector.py`: Tab 1 - Kiểm tra phần cứng toàn diện.
  - `tab_monitor.py`: Tab 2 - Serial Monitor, điều khiển thiết bị qua lệnh F1–F15, Wi-Fi và TCP Server.
  - `tab_flasher.py`: Tab 3 - Nạp đa file `.bin` với thanh tiến trình và công cụ xóa Flash.
  - `tab_partition.py`: Tab 4 - Partition Wizard với MiniTool Disk Map tương tác trực quan.
- **`modules/dialogs/`**:
  - `settings_dialog.py`: Hộp thoại cấu hình hệ thống đa tab (Chung, Phím chức năng, Cập nhật, Giới thiệu).
  - `partition_dialogs.py`: Hộp thoại thêm/sửa phân vùng và nạp mẫu phân vùng mẫu (Preset).
  - `layout_util.py`: Căn chỉnh vị trí cửa sổ con tương đối so với cửa sổ cha.

---

## 3. CƠ CHẾ AN TOÀN VÀ ĐỒNG BỘ ĐA LUỒNG (SAFETY & THREADING)

1. **Tránh xung đột cổng Serial giữa Monitor và esptool:**
   - Cổng Serial là tài nguyên đơn quyền truy cập (Exclusive Resource).
   - Khi thực hiện kiểm tra phần cứng, nạp flash, hoặc đọc/ghi phân vùng, hệ thống tự động tạm ngắt kết nối Serial Monitor (`serial_connection.close()`) và cắm cờ `is_detecting` / `is_flashing`.
   - Sau khi tác vụ esptool hoàn tất, hệ thống tự động phục hồi kết nối Serial nếu trước đó đang mở.
2. **Kiểm tra an toàn Flash trước khi ghi (Safety Checks):**
   - **Chống chồng lấn địa chỉ (Overlap Detection):** Kiểm tra dải `[Offset, Offset + Size]` của tất cả các file trước khi nạp để tránh trường hợp file này ghi đè phá hủy dữ liệu của file khác.
   - **Căn lề Sector 4 KB:** Mọi thao tác xóa vùng (`erase-region`) bắt buộc phải có địa chỉ bắt đầu và độ dài chia hết cho 4096 bytes (kích thước sector vật lý nhỏ nhất của chip Flash SPI).
3. **Luồng giao diện bất đồng bộ:**
   - Mọi hoạt động I/O tốn thời gian (kết nối mạng, tải bản cập nhật, giao tiếp cổng COM, chạy esptool) đều chạy trên background thread (`threading.Thread(daemon=True)`).
   - Dữ liệu trả về được đưa vào hàng đợi hoặc cập nhật lên UI an toàn thông qua phương thức `root.after()`.

---

## 4. BỘ KIỂM THỬ ĐƠN VỊ (UNIT TEST SUITE)

Dự án tích hợp bộ kiểm thử tự động với `pytest` bao gồm 50 ca kiểm thử:
- `tests/test_app_tabs.py`: Kiểm thử khởi tạo và tích hợp các Mixin tab.
- `tests/test_audit_regressions.py`: Kiểm thử hồi quy các lỗi đã từng rà soát trong báo cáo audit.
- `tests/test_core_utils.py`: Kiểm thử các module tiện ích cốt lõi (stream, mac_database, serial_util).
- `tests/test_partition_wizard.py`: Kiểm thử cấu trúc 32-byte, tính mã MD5, thuật toán auto_pack, validator bảng phân vùng.
- `tests/test_release_safety.py`: Kiểm thử các rào chắn an toàn khi nạp flash và xóa vùng nhớ.
- `tests/test_update_util.py`: Kiểm thử bộ so sánh phiên bản và xử lý phản hồi từ GitHub API.
