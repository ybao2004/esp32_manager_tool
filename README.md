# ESP32 Manager Tool (v1.4)

> **Tác giả:** `@ybao04` | **Bản quyền:** GNU General Public License v3.0 (GPL-3.0) | **Kho lưu trữ:** [github.com/ybao2004/esp32_manager_tool](https://github.com/ybao2004/esp32_manager_tool)

**ESP32 Manager Tool v1.4** là bộ công cụ desktop thuần **PyQt6** dành cho kỹ sư hệ thống nhúng và lập trình viên Espressif (ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C5, ESP32-C6, ESP32-H2, ESP32-P4). Ứng dụng thống nhất toàn bộ quy trình chẩn đoán phần cứng, theo dõi Serial, nạp Flash firmware, thiết kế bảng phân vùng (Partition Wizard) và sao lưu / nhân bản trực tiếp đa mạch vào một giao diện **Kỹ thuật Chuyên sâu (Engineering Sáng & Tối)**.

---

## ĐIỂM MỚI TRÊN PHIÊN BẢN v1.4

- **Chuẩn hóa logic so sánh phiên bản & đồng bộ giao diện cập nhật:** Sửa lỗi phân tích chuỗi phiên bản (`parse_version_tuple`, `is_newer_version`) trong `modules/update_util.py`, nhận diện chính xác các bản cập nhật mới khi nâng cấp từ các bản cài đặt lịch sử `v1.11` / `v1.10`; hiển thị trạng thái phát hành đồng nhất, rõ ràng trên trang Cài đặt và hộp thoại Cập nhật, loại bỏ hoàn toàn tình trạng thông báo mâu thuẫn giữa trạng thái và nhật ký phát hành.
- **Đồng bộ định danh phát hành & làm gọn kho mã nguồn:** Cập nhật đồng bộ định danh `APP_VERSION = "1.4"` xuyên suốt ứng dụng, kịch bản đóng gói và tài liệu phát hành; chỉ giữ mã nguồn ứng dụng chính trên nhánh `main` của GitHub.
- **Kế thừa toàn bộ cải tiến cốt lõi:** Cập nhật trực tiếp không đổi tên hậu tố, kịch bản tự thay thế `.exe` chạy ẩn nền hoàn toàn (`CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW`), màn hình khởi động `StartupSplash` QWidget, hỗ trợ `esptool` v4 & v5, Tab 5 sao lưu & nhân bản đa mạch song song.

---

## TÍNH NĂNG CỐT LÕI

### 1. Kiểm tra Chip (Tab 1)
- Kết nối phần cứng qua `esptool` để nhận diện chính xác dòng chip, Silicon Revision, tần số thạch anh (Crystal), các tính năng phần cứng và hệ số Flash/PSRAM.
- Đọc dung lượng Flash vật lý (RDID JEDEC), PSRAM SPI, thống kê các vùng RAM nội còn trống và định danh địa chỉ MAC (Station / AP / Bluetooth) kèm đối soát tiền tố OUI Espressif.
- Tự động tách riêng log thô `esptool` và xuất báo cáo chuẩn hóa (`.txt`).

### 2. Serial Monitor & Bảng Điều Khiển IoT (Tab 2)
- Hỗ trợ giao tiếp UART thời gian thực, tự động cuộn (`autoscroll`), gắn dấu thời gian (`timestamp`), lưu lịch sử lệnh theo phím Lên/Xuống và tự động nối lại cổng khi mất kết nối bất thường.
- Hỗ trợ cấu hình nhanh qua giao thức lệnh (Wi-Fi SSID/Mật khẩu, IP & Cổng TCP) và **15 nút điều khiển IoT (F1 - F15)** tùy biến tự do.

### 3. Nạp Firmware Flash (Tab 3)
- Cho phép nạp đồng thời tối đa **4 file `.bin`** ở các địa chỉ Offset khác nhau (hỗ trợ kéo-thả tệp trực tiếp từ Windows Explorer).
- Kiểm tra chống chồng lấn dải địa chỉ Flash (`Overlap Check`) trước khi ghi.
- Tích hợp **Xóa NVS**, **Xóa Toàn Bộ Flash** và thanh tiến trình hợp nhất dưới thanh trạng thái đáy.

### 4. Quản lý Phân vùng - Partition Wizard (Tab 4)
- Tương thích hệ số dòng chip Espressif (`chip_database.py`); chọn dòng chip tự động điền mức Flash cao nhất tương thích.
- Sơ đồ **MiniTool Disk Map** với khung viền chọn 2 lớp độ tương phản cao, hỗ trợ kéo rộng / thu hẹp, hoàn tác (`Undo`) và làm lại (`Redo`) không giới hạn trong phiên.
- Hỗ trợ 2 chế độ đơn vị (**Thập phân KB/MB** và **Thập lục phân Hex**), tự động căn lề chuẩn 4 KB / 64 KB (`Auto-Align`), nạp **Mẫu Chuẩn...**, **Quét Dự Án** từ thư mục build ESP-IDF/PlatformIO/Arduino, mở CSV/BIN, lưu toàn bảng bằng **Lưu CSV**, và đọc/ghi/dump/xóa từng phân vùng trực tiếp qua chip.

### 5. Sao lưu & Nhân bản Đa Mạch (Tab 5)
- Toàn bộ cụm nút nguồn & lọc nhanh nằm gọn trên **1 hàng ngang**; `Board Gốc` dùng chung Cổng COM ở thanh điều khiển trên cùng, trong khi **Baudrate Tab 5** giữ độc lập để đọc/chép tốc độ cao.
- Đọc toàn bộ bảng phân vùng trực tiếp từ `Board Gốc` (hiển thị cả `bootloader` và `partition_table`), hỗ trợ tích chọn từng phân vùng trên bảng hoặc trực tiếp trên sơ đồ đĩa.
- Cắt trống `0xFF` (`Smart Trim`) để tiết kiệm dung lượng sao lưu, tạo bộ hồ sơ xác thực toàn vẹn (`backup_info.txt`, `backup_manifest.json`, `partitions.csv`) chứa mã băm SHA-256 & MD5 cho từng phân vùng.
- **Nhân bản trực tiếp (Direct Multi-Board Clone):** Đọc từ `Board Gốc` hoặc thư mục sao lưu sẵn có và nạp song song ra nhiều `Board Đích` cùng lúc (tự động loại trừ cổng COM trên cùng khỏi `Board Đích`, hiển thị chính xác tiến trình `esptool` v4/v5 theo từng bước).
- **Nháy LED nhận diện Board Gốc (tùy chọn nâng cao):** Bật trong *Cài đặt -> Tùy chọn ẩn (Tab 5)* để gửi tín hiệu nháy LED TX/RX an toàn trong 5 giây khi đổi Cổng COM ở Tab 5 hoặc bấm `Nháy LED`.

### 6. Cài đặt & Cập nhật (Tab 6)
- Chuyển đổi giao diện Kỹ thuật **Sáng / Tối** trực tiếp không cần khởi động lại.
- Quản lý bộ lọc cổng COM (tự động quét định kỳ, lọc Bluetooth, ẩn danh sách cổng tùy chọn).
- Quản lý bảng phím chức năng F1 - F15 và kiểm tra/tải/cài đặt cập nhật nội tuyến ngay trong trang Cài đặt qua GitHub Releases API (`ybao2004/esp32_manager_tool`), kèm tùy chọn tự kiểm tra khi khởi động và chấm đỏ thông báo.

---

## CẤU TRÚC MÃ NGUỒN

```text
esp32_manager_tool/
├── main.py                         # Điểm khởi chạy ứng dụng PyQt6 (High-DPI & Icon Windows)
├── esp32_manager_tool.spec         # Cấu hình đóng gói PyInstaller EXE
├── build_exe.bat                   # Kịch bản build file .exe độc lập trên Windows
├── icons/                          # Icon ứng dụng (.ico, .png) & Fluent SVG icons
├── modules/
│   ├── app_core.py                 # Lớp InspectorApp, vòng đời Single-Instance & thu hồi GDI icon
│   ├── single_instance.py          # Khóa đơn thực thể (Mutex/IPC) & dừng tiến trình con hệ điều hành
│   ├── config.py                   # Cấu hình hệ thống, phiên bản (v1.4) và hằng số mặc định
│   ├── esptool_util.py             # Đóng gói tiến trình con esptool đa nền tảng & parse Output
│   ├── backup_utils.py             # Tính băm SHA-256/MD5, cắt 0xFF và đọc viết manifest sao lưu
│   ├── binary_scanner.py           # Bộ quét tệp .bin và gợi ý offset chuẩn
│   ├── serial_util.py              # Lọc cổng COM, phát hiện Bluetooth và quản lý port an toàn
│   ├── stream_util.py              # Tách log thô esptool và dòng trạng thái cho UI
│   ├── update_util.py              # Kiểm tra cập nhật GitHub Releases và tải tệp tiến trình thực
│   ├── help_content.py             # Nội dung giới thiệu & hướng dẫn nhanh tích hợp sẵn
│   ├── partition/                  # Engine Phân vùng chuẩn ESP-IDF (Model, Auto-Pack, Chip DB, Units)
│   ├── tabs/                       # Nghiệp vụ 5 Tab (Inspector, Monitor, Flasher, Partition, Backup/Clone)
│   └── ui/                         # Giao diện PyQt6: MainWindow, Pages, Dialogs, Widgets, Theme Engine
```

---

## CÀI ĐẶT & KHỞI CHẠY

1. **Cài đặt thư viện phụ thuộc:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Khởi chạy ứng dụng:**
   ```bash
   python main.py
   ```

3. **Đóng gói ra file `.exe` độc lập (Windows):**
   ```bat
   build_exe.bat
   ```
   File thực thi hoàn chỉnh sẽ được xuất tại `dist\Esp32_manager_tool.exe`.
