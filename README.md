# Esp32 manager tool (v1.0)

Ứng dụng GUI tất-cả-trong-một (All-in-One GUI Toolkit) chuyên nghiệp và gọn nhẹ dành cho kỹ sư nhúng và nhà phát triển làm việc với ESP8266 và toàn bộ các dòng chip ESP32: S2, S3, S31, C2, C3, C5, C6, C61, H2, H21, H4 và P4.

🔗 **Kho mã nguồn GitHub:** [https://github.com/ybao2004/esp32_manager_tool](https://github.com/ybao2004/esp32_manager_tool)

---

## CÁC TÍNH NĂNG CHÍNH

### 1. Kiểm Tra & Chẩn Đoán Phần Cứng Toàn Diện (Tab 1)
- Đọc Silicon Revision, tần số thạch anh ngoại vi (Crystal), ID nhà sản xuất Flash (Winbond, GigaDevice, Puya, Macronix,...), dung lượng Flash & PSRAM.
- Bóc tách Base MAC và tự động suy dẫn địa chỉ MAC Wi-Fi Station, Wi-Fi AP và Bluetooth.
- Đối soát MAC với 335 tiền tố MA-L/OUI được cấp cho Espressif.
- Tra cứu năng lực xử lý (MIPS/CoreMark), cấu trúc nhân và tài nguyên SRAM/ROM từ cơ sở dữ liệu tích hợp.
- Xuất báo cáo chẩn đoán chi tiết ra file văn bản (.txt).

### 2. Serial Monitor & Điều Khiển IoT (Tab 2)
- Bộ lọc cổng COM thông minh, tự động quét và ưu tiên chọn cổng mới cắm, lưu trạng thái cổng gần nhất.
- Tùy chọn baudrate linh hoạt cùng tính năng tự động dò tìm Baudrate thông minh.
- Bảng 15 phím chức năng (F1 -> F15) tùy biến nhãn và chuỗi lệnh gửi qua Serial.
- Hỗ trợ giao thức điều khiển mạng Wi-Fi và kết nối TCP Server từ xa qua lệnh Serial.
- Hỗ trợ Reset ESP kép: Reset mềm qua lệnh Serial kết hợp xung phần cứng DTR/RTS trên mạch nạp.

### 3. Nạp Flash Firmware (.bin) Đa File & Công Cụ Xóa (Tab 3)
- Nạp đồng thời tối đa 4 file binary (.bin) với offset tùy chỉnh và thanh tiến trình thời gian thực.
- Tự động kiểm tra tính hợp lệ và cảnh báo chống chồng lấn vùng nhớ trước khi nạp.
- Tính năng "Xóa Toàn Bộ Flash" (`erase-flash`) và "Xóa vùng Flash" (`erase-region`) theo địa chỉ với yêu cầu căn lề sector 4 KB an toàn.

### 4. Quản Lý Phân Vùng Bộ Nhớ Flash - Partition Wizard (Tab 4)
- Sơ đồ thanh ổ đĩa trực quan phong cách **MiniTool Partition Wizard** vẽ theo tỷ lệ dung lượng thực tế, hỗ trợ hover tooltip, chọn khối, menu ngữ cảnh chuột phải và click tạo phân vùng vào khoảng trống chưa phân bổ (*Unallocated Gaps*).
- Tự động dồn biên và căn chỉnh lề chuẩn 4KB / 64KB (`⚡ Dồn & Căn 4K/64K`) chỉ với 1 click.
- Kiểm tra tính hợp lệ thời gian thực (Real-Time Rule Validator) theo tiêu chuẩn ESP-IDF.
- Đọc và xuất file `partitions.csv` chuẩn ESP-IDF.
- Biên dịch trực tiếp sang file nhị phân `partition-table.bin` 32-byte struct kèm MD5 Checksum.
- Tương tác phần cứng an toàn: Đọc bảng phân vùng từ chip, nạp xuống chip, sao lưu (dump), xóa trắng (erase) và nạp file `.bin` vào từng phân vùng qua chip ESP32.

### 5. Cài Đặt Hệ Thống & Tự Động Kiểm Tra Cập Nhật
- Quản lý giao diện Sáng / Tối (Dark / Light Theme) đồng bộ toàn ứng dụng.
- Quản lý danh sách cổng COM (ẩn/hiện các cổng COM không mong muốn).
- Cấu hình mạng TCP/IP Server mặc định và gán nhãn phím điều khiển.
- **Tab Cập Nhật (Update):** Tự động kết nối GitHub Releases API (`ybao2004/esp32_manager_tool`), kiểm tra phiên bản mới, xem ghi chú phát hành (changelog) và tải trực tiếp file cập nhật về máy kèm thanh tiến trình download thời gian thực.

---

## PHẠM VI HỖ TRỢ CHIP

- **Nạp Flash / kiểm tra phần cứng / phân vùng (esptool 5.4):** ESP32, S2, S3, S31, C2, C3, C5, C6, C61, H2, H21, H4, P4 và ESP8266.
- Bộ icon v3 độ nét cao chuẩn High-DPI Windows, hiển thị sắc nét trên cả màn hình 100%, 125%, 150% và 200%.

---

## CẤU TRÚC THƯ MỤC DỰ ÁN

```
esp32_manager_tool/
├── main.py                     # Điểm khởi chạy chính của ứng dụng
├── esp32_manager_tool.spec     # Cấu hình đóng gói PyInstaller .exe
├── requirements.txt            # Danh sách thư viện phụ thuộc (esptool, pyserial)
├── .gitignore                  # Cấu hình bỏ qua file tạm cho Git
├── tests/                      # Bộ kiểm thử đơn vị & kiểm thử hồi quy
├── docs/                       # Tài liệu hướng dẫn sử dụng và báo cáo kỹ thuật
├── README.md                   # Tài liệu giới thiệu tổng quan dự án
├── icons/                      # Thư mục icon ứng dụng (.ico đa kích thước, .png)
└── modules/                    # Mã nguồn các module nghiệp vụ
    ├── app_core.py             # Bộ điều khiển trung tâm & Quản lý vòng đời ứng dụng
    ├── config.py               # Cấu hình hằng số, bảng màu & CSDL thông số chip
    ├── update_util.py          # Kiểm tra và tải cập nhật tự động từ GitHub Releases
    ├── binary_scanner.py       # Bộ kiểm tra tính hợp lệ và quét phân đoạn file .bin
    ├── esptool_util.py         # Wrapper giao tiếp đa luồng an toàn với esptool
    ├── mac_database.py         # CSDL 335 tiền tố OUI Espressif phục vụ đối soát MAC
    ├── serial_util.py          # Tiện ích quét và liệt kê cổng Serial máy tính
    ├── stream_util.py          # Bộ đón bắt luồng output và lọc mã màu ANSI thời gian thực
    ├── win32_util.py           # Tiện ích Win32 API thiết lập icon sắc nét High-DPI
    ├── help_content.py         # Nội dung hướng dẫn sử dụng tích hợp trong ứng dụng
    ├── partition/              # Engine lõi quản lý phân vùng ESP32
    │   ├── partition_model.py  # Cấu trúc dữ liệu, đọc/xuất CSV, Struct 32-byte BIN, MD5
    │   ├── chip_database.py    # CSDL thông số các dòng chip Espressif
    │   ├── unit_formatter.py   # Bộ phân tích & quy đổi đơn vị (DEC, HEX, DUAL, Sector 4KB)
    │   └── project_scanner.py  # Bộ quét tự động dự án ESP-IDF / PlatformIO
    ├── dialogs/
    │   ├── layout_util.py      # Tiện ích bố cục hộp thoại đáp ứng theo kích thước
    │   ├── settings_dialog.py  # Cửa sổ Cài đặt hệ thống, phím chức năng & Cập nhật
    │   └── partition_dialogs.py# Hộp thoại Thêm/Sửa phân vùng & Chọn mẫu Preset
    └── tabs/
        ├── tab_inspector.py    # Tab 1: Kiểm tra Phần cứng
        ├── tab_monitor.py      # Tab 2: Serial Monitor & Điều khiển IoT
        ├── tab_flasher.py      # Tab 3: Nạp Flash Firmware (.bin)
        └── tab_partition.py    # Tab 4: Phân vùng Bộ nhớ (Partition Wizard)
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
   pytest
   ```
