# Hướng dẫn sử dụng Esp32 manager tool (v1.3)

Ứng dụng GUI tất-cả-trong-một (All-in-One GUI Toolkit) chuyên nghiệp và gọn nhẹ dành cho kỹ sư nhúng và nhà phát triển làm việc với ESP8266 và toàn bộ các dòng chip ESP32 (S2, S3, C2, C3, C5, C6, H2, P4,...).

---

## KHỞI CHẠY ỨNG DỤNG

1. **Khởi chạy từ mã nguồn Python:**
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
2. **Khởi chạy file thực thi độc lập (Standalone Portable EXE):**
   ```bash
   esp32_manager_tool.exe
   ```

---

## 1. KIỂM TRA & CHẨN ĐOÁN PHẦN CỨNG (TAB 1)

1. **Kết nối phần cứng:**
   - Chọn cổng **COM Port** tương ứng với mạch ESP đang cắm vào máy tính.
   - Chọn **Baudrate** (khuyến nghị để `Tự động` hoặc `115200`).
2. **Thực hiện kiểm tra:**
   - Bấm **KIỂM TRA TOÀN DIỆN**.
   - Ứng dụng sẽ đồng bộ với bootloader ROM của ESP và phân tích:
     - **Thông tin chip:** Chip Model, Silicon Revision, Crystal Frequency, ID nhà sản xuất Flash (Winbond, GigaDevice, Puya, Macronix,...), dung lượng Flash và PSRAM.
     - **Địa chỉ MAC:** Base MAC, MAC Wi-Fi Station, MAC Wi-Fi AP và MAC Bluetooth.
     - **Đối soát OUI:** Đối soát tiền tố MA-L/OUI với cơ sở dữ liệu hơn 335 dải MAC của Espressif.
     - **Bảng thông số kỹ thuật:** Kiến trúc CPU, số nhân, tần số tối đa, năng lực tính toán MIPS/CoreMark, SRAM, ROM.
3. **Tiện ích:**
   - Tích chọn **Hiển thị Output Thô** để xem chi tiết log trả về từ `esptool`.
   - Bấm **Lưu Báo Cáo** để xuất toàn bộ kết quả chẩn đoán ra file văn bản `.txt`.

---

## 2. SERIAL MONITOR & ĐIỀU KHIỂN IOT (TAB 2)

1. **Kết nối Serial:**
   - Chọn cổng COM và Baudrate ở thanh điều khiển trên cùng, bấm **Kết nối**.
   - Màn hình Serial hiển thị dữ liệu truyền nhận từ thiết bị theo thời gian thực.
   - Hỗ trợ **Tự động cuộn** và **Thêm Dấu thời gian** (timestamp).
   - Bộ lọc cổng COM thông minh, tự động phát hiện cổng mới cắm và ghi nhớ cấu hình cổng gần nhất.
2. **Gửi dữ liệu Serial:**
   - Nhập chuỗi tại ô nhập liệu bên dưới.
   - Bấm **Enter** để gửi lệnh, hoặc **Shift + Enter** để xuống dòng.
   - Nút **Reset ESP** sẽ gửi chuỗi lệnh `RESET` đồng thời kích hoạt xung phần cứng DTR/RTS trên cổng nạp để khởi động lại chip.
3. **Bảng phím điều khiển (F1 -> F15):**
   - 15 nút chức năng tùy biến cho phép gửi nhanh các chuỗi lệnh cấu hình định sẵn.
   - Tùy biến nhãn hiển thị và nội dung lệnh tương ứng trong menu **Cài đặt -> Nút chức năng**.
4. **Cấu hình mạng Wi-Fi & TCP Server:**
   - Bấm **Quét WiFi** để yêu cầu vi điều khiển quét danh sách mạng khả dụng.
   - Nhập mật khẩu, bấm **Kết nối WiFi** để gửi cấu hình kết nối.
   - Nhập IP Server và Cổng, bấm **Kết nối Server** để vi điều khiển thiết lập socket TCP.

---

## 3. NẠP FLASH FIRMWARE (.BIN) & CÔNG CỤ XÓA (TAB 3)

1. **Cấu hình nạp chung:**
   - **Mục tiêu Chip:** Chọn chip mục tiêu (mặc định `auto` để esptool tự nhận diện).
   - **Tốc độ Nạp (Baud):** Khuyến nghị `460800` hoặc `921600` để nạp nhanh, hoặc `115200` nếu cáp truyền tín hiệu kém.
   - Tùy chọn **Xóa sạch Flash trước khi nạp (--erase-all)** nếu muốn format trắng bộ nhớ trước khi ghi.
2. **Danh sách File nạp:**
   - Hỗ trợ nạp đồng thời tối đa 4 file binary (.bin) cùng lúc.
   - Bấm **Chọn File...** để duyệt tìm file `.bin` trên máy tính.
   - Điền địa chỉ **Offset** nạp tương ứng (ví dụ: `0x1000` cho Bootloader, `0x8000` cho Partitions, `0xe000` cho Boot App0, `0x10000` cho Firmware ứng dụng).
   - Tích chọn ô kích hoạt cho các file muốn nạp.
   - Ứng dụng tự động kiểm tra tính hợp lệ và cảnh báo chống chồng lấn vùng nhớ (*Address Overlap Check*).
3. **Tiến trình nạp:**
   - Bấm nút **BẮT ĐẦU NẠP FLASH**.
   - Theo dõi thanh tiến trình phần trăm (%) và log chi tiết thời gian thực.
4. **Công cụ Xóa Flash an toàn:**
   - **Xóa Toàn Bộ Flash:** Format trắng toàn bộ bộ nhớ flash vật lý của chip.
   - **Xóa vùng Flash:** Xóa một vùng bộ nhớ cụ thể theo Offset và kích thước xác định (yêu cầu địa chỉ và độ dài chia hết cho sector 4 KB = `0x1000` an toàn).

---

## 4. QUẢN LÝ PHÂN VÙNG BỘ NHỚ FLASH - PARTITION WIZARD (TAB 4)

1. **Sơ đồ thanh ổ đĩa trực quan (MiniTool Disk Map):**
   - Biểu diễn trực quan tỷ lệ các phân vùng trên toàn bộ dung lượng chip Flash.
   - Tự động nhận diện các khoảng trống chưa phân bổ (*Unallocated Gaps*).
   - Click chọn khối để highlight trong bảng; nhấp vào khoảng trống để tạo phân vùng mới ngay tại vị trí đó; hover chuột để xem thông số chi tiết qua Tooltip.
   - Menu chuột phải trên từng khối: Thêm, Sửa, Xóa, Sao lưu (Dump), Xóa trắng (Erase) hoặc Nạp trực tiếp file `.bin`.
2. **Bộ công cụ tự động căn lề (`⚡ Dồn & Căn 4K/64K`):**
   - Tự động tính toán lại toàn bộ Offset nối tiếp nhau, đảm bảo căn lề chuẩn 64 KB (`0x10000`) cho phân vùng App và 4 KB (`0x1000`) cho phân vùng Data.
3. **Kiểm tra tính hợp lệ thời gian thực (Real-Time Validator):**
   - Cảnh báo trùng lặp tên, sai định dạng, phân vùng App đặt dưới `0x10000`, thiếu phân vùng `otadata` khi có `ota_X`, hoặc tổng dung lượng vượt quá kích thước chip Flash.
4. **Nhập/Xuất & Biên dịch nhị phân:**
   - Hỗ trợ nhập và xuất file `partitions.csv` chuẩn ESP-IDF.
   - Biên dịch trực tiếp bảng phân vùng sang file nhị phân `partition-table.bin` 32-byte struct kèm MD5 Checksum.
   - Hỗ trợ nạp bảng mẫu preset nhanh (Default 4MB, Large App, Minimal SPIFFS, 8MB/16MB OTA,...).
5. **Tương tác phần cứng an toàn:**
   - Đọc bảng phân vùng trực tiếp từ chip ESP đang kết nối.
   - Nạp bảng phân vùng xuống chip tại địa chỉ `0x8000`.
   - Sao lưu (Dump) phân vùng ra file `.bin`, Xóa trắng (Erase) hoặc nạp file binary vào từng phân vùng độc lập.
   - Tự động ngắt và khôi phục Serial Monitor để tránh xung đột cổng COM.
   - Chi tiết xem tại: [HUONG_DAN_PHAN_VUNG.md](HUONG_DAN_PHAN_VUNG.md).

---

## 5. CÀI ĐẶT HỆ THỐNG & TỰ ĐỘNG CẬP NHẬT

Bấm nút **Cài đặt** ở góc trên bên phải giao diện để mở cửa sổ cấu hình đa tab:

1. **Cài đặt chung:**
   - **Giao diện:** Chuyển đổi giữa chế độ **Sáng (Light)** và **Tối (Dark)** đồng bộ toàn hệ thống.
   - **Quản lý cổng COM:** Lọc và ẩn các cổng COM ảo hoặc thiết bị không mong muốn; tùy chọn tự động chọn cổng mới cắm.
   - **Mạng mặc định:** Cấu hình IP và Port máy chủ TCP mặc định cho Tab Monitor.
2. **Nút chức năng:**
   - Tùy biến nhãn hiển thị và câu lệnh gửi đi cho 15 phím chức năng `F1` đến `F15`.
3. **Cập nhật (Update):**
   - Tích hợp kết nối trực tiếp với GitHub Releases API (`ybao2004/esp32_manager_tool`).
   - Kiểm tra phiên bản mới nhất, xem ghi chú phát hành (Changelog).
   - Tải trực tiếp file cập nhật mới nhất về máy với thanh tiến trình download thời gian thực.
4. **Hướng dẫn sử dụng & Giới thiệu:**
   - Xem hướng dẫn nhanh tích hợp và thông tin bản quyền ứng dụng.
5. **Khôi phục gốc:**
   - Đưa toàn bộ cấu hình về trạng thái mặc định của nhà sản xuất.
