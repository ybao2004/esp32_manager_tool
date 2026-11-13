# ESP32 Manager Tool (v1.7)

> **Tác giả:** `@ybao04` | **Bản quyền:** GNU General Public License v3.0 (GPL-3.0) | **Kho lưu trữ:** [github.com/ybao2004/esp32_manager_tool](https://github.com/ybao2004/esp32_manager_tool)

**ESP32 Manager Tool v1.7** là bộ công cụ desktop thuần **PyQt6** dành cho kỹ sư hệ thống nhúng và lập trình viên Espressif (ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C5, ESP32-C6, ESP32-H2, ESP32-P4). Ứng dụng thống nhất toàn bộ quy trình chẩn đoán phần cứng, theo dõi Serial, nạp Flash firmware, thiết kế bảng phân vùng (Partition Wizard) và sao lưu / nhân bản trực tiếp đa mạch vào một giao diện **Kỹ thuật Chuyên sâu (Engineering Sáng & Tối)**.

---

## ĐIỂM MỚI TRÊN PHIÊN BẢN v1.7

- **Thuần PyQt6 100% (Loại bỏ hoàn toàn Tkinter):** Kiến trúc giao diện hiện đại hóa hoàn chỉnh trên PyQt6 với thanh điều hướng dọc (Sidebar) có thể thu gọn, thẻ nhóm nội dung `Card`, biểu tượng vector `QSvgRenderer` tự đổi màu sắc nét theo chế độ Sáng/Tối và hỗ trợ icon gốc trên Windows Taskbar (`AppUserModelID` + `WM_SETICON`).
- **Phong cách Kỹ thuật Chuyên sâu (Engineering Sáng / Tối):** Giữ duy nhất phong cách Engineering cân đối, loại bỏ viền focus xanh gây rối trong bảng chỉnh sửa, vẽ Checkbox/Radio bằng vector chuẩn xác (`EngineeringProxyStyle`) và tinh chỉnh tương phản trên cả nền Sáng lẫn Tối.
- **Thanh tiến trình thống nhất ở đáy (Unified Status Progress):** Đồng bộ hóa tiến trình thời gian thực (0% -> 100%) kèm nhãn mô tả tác vụ trực tiếp trên thanh trạng thái đáy cho các Tab 1, Tab 3, Tab 4 và Tab 5.
- **Cải tiến Tab 4 (Phân vùng Bộ nhớ):** Khởi tạo sạch (trống cho đến khi nạp mẫu/mở tệp/đọc chip/thêm dòng), chọn chip tự động chọn dung lượng Flash cao nhất tương ứng, nút `+ Thêm dòng` chèn ngay sau phân vùng đang chọn, đơn giản hóa thao tác lưu chỉ với nút **Lưu CSV** (lưu toàn bảng và lưu đè tệp CSV đang mở).
- **Cải tiến Tab 5 (Sao lưu & Nhân bản):** Khởi tạo trống trước khi đọc chip nguồn, bổ sung tùy chọn nâng cao trong Cài đặt giúp tự nháy LED 5 giây khi chọn `Board Gốc` và hiện nút **Nháy LED** (không kích hoạt xung DTR/RTS gây reset mạch).

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
- Đọc toàn bộ bảng phân vùng trực tiếp từ `Board Gốc` (hiển thị cả `bootloader` và `partition_table`), hỗ trợ tích chọn từng phân vùng trên bảng hoặc trực tiếp trên sơ đồ đĩa.
- Cắt trống `0xFF` (`Smart Trim`) để tiết kiệm dung lượng sao lưu, tạo bộ hồ sơ xác thực toàn vẹn (`backup_info.txt`, `backup_manifest.json`, `partitions.csv`) chứa mã băm SHA-256 & MD5 cho từng phân vùng.
- **Nhân bản trực tiếp (Direct Multi-Board Clone):** Đọc từ `Board Gốc` hoặc thư mục sao lưu sẵn có và nạp song song ra nhiều `Board Đích` cùng lúc (mặc định giữ nguyên vùng `nvs` / `otadata` tùy chọn theo nhu cầu).
- **Nháy LED nhận diện Board Gốc (tùy chọn nâng cao):** Bật trong *Cài đặt -> Tùy chọn ẩn (Tab 5)* để gửi tín hiệu nháy LED TX/RX an toàn trong 5 giây khi chọn board nguồn hoặc bấm `Nháy LED`.

### 6. Cài đặt & Cập nhật (Tab 6)
- Chuyển đổi giao diện Kỹ thuật **Sáng / Tối** trực tiếp không cần khởi động lại.
- Quản lý bộ lọc cổng COM (tự động quét định kỳ, lọc Bluetooth, ẩn danh sách cổng tùy chọn).
- Quản lý bảng phím chức năng F1 - F15 và kiểm tra/tải cập nhật tự động qua GitHub Releases API (`ybao2004/esp32_manager_tool`).

---

## CẤU TRÚC MÃ NGUỒN

```text
esp32_manager_tool/
├── main.py                         # Điểm khởi chạy ứng dụng PyQt6 (High-DPI & Icon Windows)
├── esp32_manager_tool.spec         # Cấu hình đóng gói PyInstaller EXE
├── build_exe.bat                   # Kịch bản build file .exe độc lập trên Windows
├── assets/                         # Icon ứng dụng (.ico, .png)
├── icons/fluent/                   # Kho biểu tượng vector SVG Fluent System Icons
├── docs/                           # Tài liệu hướng dẫn & kiến trúc hệ thống
├── modules/
│   ├── app_core.py                 # Lớp chính InspectorApp kế thừa MainWindow + 5 Tab Mixin
│   ├── config.py                   # Cấu hình hệ thống, phiên bản (v1.7) và hằng số mặc định
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
└── tests/                          # Bộ kiểm thử tự động pytest (mock hardware + offscreen PyQt6)
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

3. **Chạy kiểm thử tự động:**
   ```bash
   pytest -q
   ```

4. **Đóng gói ra file `.exe` độc lập (Windows):**
   ```bat
   build_exe.bat
   ```
   File thực thi hoàn chỉnh sẽ được xuất tại `dist\Esp32_manager_tool.exe`.

---

## TÀI LIỆU DỰ ÁN

- [Hướng dẫn sử dụng toàn diện](docs/HUONG_DAN_SU_DUNG.md) - Chi tiết từng Tab và Hộp thoại trong phiên bản v1.7.
- [Hướng dẫn Quản lý Phân vùng (Partition Wizard)](docs/HUONG_DAN_PHAN_VUNG.md) - Kiến trúc phân vùng ESP32, MiniTool Disk Map, Thêm dòng, Lưu CSV và thao tác Chip.
- [Kiến trúc hệ thống & Thiết kế phần mềm](docs/KIEN_TRUC_HE_THONG.md) - Kiến trúc thuần PyQt6, Mixin Controller, Theme Engine & An toàn đa luồng.
- [Báo cáo rà soát mã nguồn & Kiểm thử](docs/AUDIT_2026-09-05.md) - Lịch sử rà soát an toàn và kiểm thử hồi quy.
- [Đặc tả Icon High-DPI v3](docs/ICON_V3.md) - Đặc tả bộ biểu tượng ứng dụng đa độ phân giải.
