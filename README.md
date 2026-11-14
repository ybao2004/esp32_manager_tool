# ESP32 Manager Tool (v1.6)

> **Tác giả:** `@ybao04` | **Bản quyền:** GNU General Public License v3.0 (GPL-3.0) | **Kho lưu trữ:** [github.com/ybao2004/esp32_manager_tool](https://github.com/ybao2004/esp32_manager_tool)

**ESP32 Manager Tool v1.6** là bộ công cụ desktop thuần **PyQt6** dành cho kỹ sư hệ thống nhúng và lập trình viên Espressif (ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C5, ESP32-C6, ESP32-C61, ESP32-H2, ESP32-P4). Ứng dụng thống nhất toàn bộ quy trình chẩn đoán phần cứng, theo dõi Serial, nạp Flash firmware, thiết kế bảng phân vùng (Partition Wizard) và sao lưu / quản trị dữ liệu phân vùng / nhân bản đa mạch vào một giao diện **Kỹ thuật Chuyên sâu (Engineering Sáng & Tối)**.

---

## ĐIỂM MỚI TRÊN PHIÊN BẢN v1.6

- **Hiển thị đầy đủ 3 tầng bộ nhớ (Flash · SRAM · PSRAM):**
  - Thanh trạng thái đầu ứng dụng (`ConnectionBar`), thẻ KPI trang Kiểm tra Chip và tóm tắt ở tab Sao lưu & Chép đều hiển thị đồng bộ **Flash, SRAM nội và PSRAM** (kèm ROM khởi động trong báo cáo chi tiết).
  - Bổ sung giải mã eFuse & package mở rộng cho **ESP32-S3** và các dòng ESP32 khác (hãng/mật độ/tốc độ/chế độ bus OPI-QSPI/điện áp `VDD_SPI`), đồng thời tổng hợp metadata PSRAM và nhận diện cấu hình build (`FQBN`, board target, ngoại vi như màn hình `ILI9341`, cảm ứng `Touch I2C`, `LVGL`, `SD`, `Microphone`) từ `.rodata` ngay cả khi firmware tắt boot log (`DebugLevel=none`).
- **Khắc phục lỗi sao lưu toàn bộ Flash (`Packet content transfer stopped`) qua USB-Serial/JTAG:**
  - Vá cơ chế `read_flash` với **stateful SLIP reader** gửi xung ACK nudge khi FIFO USB 64-byte bị chững, chia khối 2 MB kiểm chứng MD5 từng chặng, tự vô hiệu hóa watchdog và tự đồng bộ/thử lại an toàn khi mất nhịp gói tin.

### Các cập nhật trước đó (v1.5.2)

- **Căn giữa đồng bộ tiêu đề bảng phân vùng (Tab 4 & Tab 5):** Toàn bộ tiêu đề cột (`Chọn`, `STT`, `Tên Vùng`, `Kiểu`, `Phân loại`, `Offset`, `Dung lượng`...) được căn giữa đều đặn trong `_TreeviewCompat`.
- **Thụt lề treo (Hanging Indent) cho khung Nhật Ký (`LogView`):** Tự động căn thẳng cột nội dung khi các dòng thụt lề (`  + `, `    -> `, `>>> `, Tab 2 `Log`) xuống dòng trên khung hẹp, bỏ dòng trống thừa ở đầu khung log và chuẩn hóa thụt lề chi tiết ở Tab 5.

## ĐIỂM MỚI TRÊN PHIÊN BẢN v1.5.1

- **Cửa sổ Giới thiệu & Bản quyền mới (`AboutDialog`):** Bố cục Hero Banner với biểu tượng ứng dụng, huy hiệu phiên bản/giấy phép/tác giả, liên kết GitHub bấm mở trực tiếp kèm nút sao chép link, lưới 6 thẻ tính năng trực quan theo từng tab và dải nền tảng công nghệ đồng bộ Sáng/Tối.
- **Loại bỏ đường kẻ phân cách `===` / `---` dư thừa:** Làm sạch toàn bộ tiêu đề nhật ký trên Tab 1 (Log Thô), Tab 2 (`Log`), Tab 3, Tab 4, Tab 5, Sổ tay phân vùng, Ghi chú cập nhật và tệp `backup_info.txt`; nâng cấp Tooltip sơ đồ `DiskMap` sang **Rich HTML** sắc nét (sửa lỗi hiển thị lặp byte dung lượng).
- **Tab 4 — Sửa nút `Xóa tất cả` & Chặn tràn dung lượng Flash:** Khắc phục lỗi nút `Xóa tất cả` không xóa bảng phân vùng; tự động tắt nút `+ Thêm dòng` và chặn cứng thao tác thêm/chèn/lưu trong `PartitionEditDialog` khi bộ nhớ trống khả dụng `< 4 KB` hoặc vượt quá dung lượng chip Flash đã chọn.
- **Tab 5 — Tinh gọn bảng phân vùng:** Gỡ cột `Mã SHA-256 / Trạng thái` dư thừa khỏi bảng hiển thị (vẫn tính và ghi đầy đủ MD5/SHA-256 vào nhật ký và `backup_manifest.json` / `backup_info.txt`).

## ĐIỂM MỚI TRÊN PHIÊN BẢN v1.5

- **Tab 2 — Serial Monitor & Log (Chia 2 sub-tab `Serial` & `Log`):**
  - **Sub-tab `Serial`:** Giữ nguyên Terminal UART thời gian thực, gửi lệnh, điều khiển Wi-Fi/TCP và 15 nút F1–F15 (tách biệt hoàn toàn khỏi log phân vùng).
  - **Sub-tab `Log`:** Tập trung nhật ký hoạt động từ **Tab 1 (`[Kiểm tra Chip]`)**, **Tab 3 (`[Nạp Firmware]`)**, **Tab 4 (`[Phân vùng]`)**, và **Tab 5 (`[Sao lưu & Chép]`)** với `[Tên Tab]` ở đầu mỗi dòng, kèm bộ lọc nguồn tab, bật/tắt dấu thời gian, tự động cuộn, `Lưu Log (.txt)` và `Xóa Log`.
- **Tab 5 — Trình Đọc / Xem & Sửa / Nạp Đè & Xóa Dữ Liệu Phân Vùng Non-Firmware + Menu Chuột Phải Đồng Bộ:** Hỗ trợ đọc xem, phân tích/sửa NVS Key-Value (parser/encoder thuần Python v1/v2), trình xem/sửa Hex & UTF-8 phân trang 16 KB (nhấp đúp dòng bảng hoặc khối DiskMap để mở nhanh), xuất nhanh `.bin`, nạp đè `.bin` ngoài và xóa dữ liệu vùng Non-Firmware (`nvs`, `spiffs`, `littlefs`, `fat`, `coredump`, `otadata`, `phy`...); tự động khóa an toàn đối với Bootloader, Partition Table và Firmware `app`. Căn thẳng cột bảng sao lưu, chỉ bật/tắt chọn khi bấm đúng cột 0 (`Chọn`) hoặc phím `Space`.
- **Chuẩn hóa quy tắc đặt tên tệp sao lưu:** Full Flash theo mẫu `<tên chip gốc>_<MAC gốc>_Full - <yyyymmdd_hhmmss>.bin` (tự nhận diện chip & MAC trước khi mở hộp thoại Lưu); từng phân vùng theo mẫu `<tên chip gốc>_<MAC gốc>_<tên phân vùng>_<offset> - <yyyymmdd_hhmmss>.bin`.
- **Tinh gọn & đồng bộ giao diện Tab 1, Tab 3, Tab 4, Tab 5 & Cài đặt:**
  - *Tab 1 (Kiểm tra Chip):* Chuyển ghi chú đối soát OUI xuống ngay dưới dòng `"Tiền tố được cấp cho Espressif (...)"` ở cả hai chế độ Báo cáo Liền mạch và Bảng Thông số; ghi 2 mốc tóm tắt `[Kiểm tra Chip]` sang Tab 2 -> `Log`.
  - *Tab 3 (Nạp Firmware):* Loại bỏ nút `Xóa vùng nhớ`, giữ trọn `Xóa toàn bộ Flash` và `Xóa toàn bộ trước khi nạp`.
  - *Tab 4 (Phân vùng):* Gom thanh công cụ gọn thành **1 hàng** với ô chọn Chip/Flash cố định kích thước (`auto` dò tự động khi bấm `Đọc từ chip`), nhấp đúp phân vùng để mở sửa, bỏ 4 nút thao tác flash trùng với Tab 5, xóa khung *Nhật Ký Thao Tác Phần Cứng Phân Vùng* dưới đáy để tối ưu không gian bảng phân vùng.
  - *Cài đặt & Cập nhật:* Loại bỏ thanh menu bar trùng lặp phía trên cùng; gom **Tự căn 4K/64K** và **Đơn vị hiển thị** về trang Cài đặt (dùng chung cho Tab 4 & Tab 5); đổi icon nút `Hủy tải` thành dấu `X`; chuẩn hóa môi trường con khi tự cập nhật `.exe` PyInstaller `--onefile` (`_MEI*`).

---

## TÍNH NĂNG CỐT LÕI

### 1. Kiểm tra Chip (Tab 1)
- Kết nối phần cứng qua `esptool` để nhận diện chính xác dòng chip, Silicon Revision, tần số thạch anh (Crystal), các tính năng phần cứng và hệ số Flash/PSRAM.
- Đọc dung lượng Flash vật lý (RDID JEDEC), PSRAM SPI, thống kê các vùng RAM nội còn trống và định danh địa chỉ MAC (Station / AP / Bluetooth) kèm đối soát tiền tố OUI Espressif.
- Tự động tách riêng log thô `esptool`, xuất báo cáo chuẩn hóa (`.txt`) và ghi 2 mốc tóm tắt sang `Serial Monitor & Log`.

### 2. Serial Monitor & Log (Tab 2)
- **Sub-tab `Serial`:** Giao tiếp UART thời gian thực, tự động cuộn (`autoscroll`), gắn dấu thời gian (`timestamp`), lưu lịch sử lệnh theo phím Lên/Xuống, tự động nối lại cổng khi mất kết nối bất thường, điều khiển Wi-Fi/TCP và **15 nút điều khiển IoT (F1 - F15)** tùy biến tự do.
- **Sub-tab `Log`:** Nhật ký hoạt động tổng hợp gắn tiền tố `[Tên Tab]` ở đầu dòng từ Tab 1, Tab 3, Tab 4 và Tab 5 kèm lọc nguồn tab, bật/tắt timestamp, `Lưu Log (.txt)` và `Xóa Log`.

### 3. Nạp Firmware Flash (Tab 3)
- Cho phép nạp đồng thời tối đa **4 file `.bin`** ở các địa chỉ Offset khác nhau (hỗ trợ kéo-thả tệp trực tiếp từ Windows Explorer).
- Kiểm tra chống chồng lấn dải địa chỉ Flash (`Overlap Check`) trước khi ghi.
- Tích hợp **Xóa Toàn Bộ Flash**, **Xóa toàn bộ trước khi nạp**, thanh tiến trình hợp nhất dưới thanh trạng thái đáy và phản chiếu log sang Tab 2 -> `Log`.

### 4. Quản lý Phân vùng - Partition Wizard (Tab 4)
- Tương thích hệ số dòng chip Espressif (`chip_database.py`); mặc định `auto` tự nhận diện Chip & Flash khi bấm **Đọc từ chip**.
- Sơ đồ **Disk Map** (chiều cao 42px căn giữa) với khung viền chọn 2 lớp độ tương phản cao, nhấp đúp bảng hoặc DiskMap để sửa phân vùng, hỗ trợ hoàn tác (`Undo`) và làm lại (`Redo`) không giới hạn trong phiên.
- Thanh công cụ gọn **1 hàng** cố định khung chọn Chip/Flash, nút **Đọc từ chip**, nạp **Mẫu**, **Quét Dự Án**, mở CSV/BIN và lưu toàn bảng bằng **Lưu CSV** (cấu hình **Đơn vị hiển thị** & **Tự căn 4K/64K** nằm trong *Cài đặt*).

### 5. Sao lưu & Nhân bản Đa Mạch (Tab 5)
- Toàn bộ cụm nút nguồn & lọc nhanh nằm gọn trên **1 hàng ngang**; `Board Gốc` dùng chung Cổng COM ở thanh điều khiển trên cùng, trong khi **Baudrate Tab 5** giữ độc lập để đọc/chép tốc độ cao.
- Đọc toàn bộ bảng phân vùng trực tiếp từ `Board Gốc` (hiển thị cả `bootloader` và `partition_table`), tích chọn từng phân vùng qua hộp kiểm cột 0 (`Chọn`) hoặc phím `Space`.
- Quản trị dữ liệu phân vùng **Non-Firmware** (`nvs`, `spiffs`, `littlefs`, `fat`...) qua nút chức năng, nhấp đúp hoặc Menu chuột phải đồng bộ giữa bảng và sơ đồ đĩa: **Đọc / Xem & Sửa NVS Key-Value & Hex/UTF-8**, **Xuất nhanh (.bin)**, **Nạp `.bin` ghi đè vùng**, **Xóa dữ liệu vùng** (khóa an toàn Bootloader, Partition Table và App).
- Đặt tên sao lưu theo chuẩn `<chip>_<MAC>_Full - <yyyymmdd_hhmmss>.bin` (Full Flash) và `<chip>_<MAC>_<tên phân vùng>_<offset> - <yyyymmdd_hhmmss>.bin` (phân vùng); cắt trống `0xFF` (`Smart Trim`) và xuất hồ sơ băm SHA-256 & MD5 (`backup_info.txt`, `backup_manifest.json`, `partitions.csv`).
- **Nhân bản trực tiếp (Direct Multi-Board Clone):** Đọc từ `Board Gốc` hoặc thư mục sao lưu sẵn có và nạp song song ra nhiều cổng Đích (`COMxx`) cùng lúc (tự động loại trừ cổng COM trên cùng, hiển thị chính xác tiến trình `esptool` v4/v5 theo từng bước).
- **Nháy LED nhận diện Board Gốc (tùy chọn nâng cao):** Bật trong *Cài đặt -> Tùy chọn ẩn (Tab 5)* để gửi tín hiệu nháy LED TX/RX an toàn trong 5 giây khi đổi Cổng COM ở Tab 5 hoặc bấm `Nháy LED`.

### 6. Cài đặt & Cập nhật (Tab 6)
- Chuyển đổi giao diện Kỹ thuật **Sáng / Tối** trực tiếp không cần khởi động lại.
- Quản lý bộ lọc cổng COM (tự động quét định kỳ, lọc Bluetooth, ẩn danh sách cổng tùy chọn), tùy chọn **Tự căn 4K/64K** & **Đơn vị hiển thị** dùng chung cho Tab 4 & Tab 5.
- Quản lý bảng phím chức năng F1 - F15 và kiểm tra/tải/cài đặt cập nhật nội tuyến ngay trong trang Cài đặt qua GitHub Releases API (`ybao2004/esp32_manager_tool`), kèm tùy chọn tự kiểm tra khi khởi động, nút `Thông tin & Bản quyền` và chấm đỏ thông báo.

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
│   ├── config.py                   # Cấu hình hệ thống, phiên bản (v1.5) và hằng số mặc định
│   ├── esptool_util.py             # Đóng gói tiến trình con esptool đa nền tảng & parse Output
│   ├── backup_utils.py             # Tính băm SHA-256/MD5, cắt 0xFF, chuẩn hóa tên file & manifest sao lưu
│   ├── nvs_util.py                 # Bộ giải mã & đóng gói NVS Binary v1/v2 thuần Python
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
