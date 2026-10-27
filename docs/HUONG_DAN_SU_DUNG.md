# Hướng dẫn sử dụng ESP Tool & Hardware Inspector v2.0

## KHỞI CHẠY ỨNG DỤNG
- Chạy trực tiếp từ mã nguồn: `python ESP_tool_v2.0.py`
- Hoặc chạy file thực thi đã đóng gói: `ESP_tool_v2.0.exe`

---

## 1. KIỂM TRA PHẦN CỨNG (TAB 1)
1. Chọn cổng **COM Port** tương ứng với mạch ESP đang cắm.
2. Chọn **Baudrate** (khuyến nghị để `Tự động` hoặc `115200`).
3. Bấm **KIỂM TRA TOÀN DIỆN**.
4. Ứng dụng sẽ đồng bộ với bootloader ROM của ESP và phân tích:
   - Thông tin động: Chip Model, Silicon Revision, Crystal Frequency, ID nhà sản xuất Flash, dung lượng Flash và PSRAM.
   - Địa chỉ MAC: Base MAC, MAC Wi-Fi Station, MAC Wi-Fi AP và MAC Bluetooth.
   - Đối soát tiền tố OUI với cơ sở dữ liệu nhà sản xuất Espressif.
   - Bảng thông số kỹ thuật tra cứu: Kiến trúc CPU, số nhân, tần số tối đa, năng lực tính toán MIPS/CoreMark, SRAM, ROM.
5. Có thể tích chọn **Hiển thị Output Thô** để xem chi tiết log trả về từ `esptool`.
6. Bấm **Lưu Báo Cáo** để xuất toàn bộ kết quả chẩn đoán ra file `.txt`.

---

## 2. SERIAL MONITOR & ĐIỀU KHIỂN (TAB 2)
1. **Kết nối Serial:**
   - Chọn cổng COM và Baudrate ở thanh điều khiển trên cùng, bấm **Kết nối**.
   - Màn hình Serial sẽ hiển thị dữ liệu truyền nhận từ thiết bị theo thời gian thực.
   - Hỗ trợ **Tự động cuộn** và **Thêm Dấu thời gian** (timestamp).
2. **Gửi dữ liệu Serial:**
   - Nhập chuỗi tại ô nhập liệu bên dưới.
   - Bấm **Enter** để gửi, hoặc **Shift + Enter** để xuống dòng.
   - Nút **Reset ESP** sẽ gửi chuỗi lệnh `RESET` đồng thời kích hoạt xung phần cứng DTR/RTS trên cổng nạp để khởi động lại chip.
3. **Bảng điều khiển (F1 -> F15):**
   - 15 nút chức năng tùy biến cho phép gửi nhanh các chuỗi lệnh cấu hình.
   - Có thể thay đổi nhãn hiển thị và nội dung lệnh tương ứng trong menu **Cài đặt -> Nút chức năng**.
4. **Cấu hình mạng Wi-Fi & TCP Server:**
   - Bấm **Quét WiFi** để yêu cầu vi điều khiển quét danh sách mạng khả dụng.
   - Nhập mật khẩu, bấm **Kết nối WiFi** để gửi cấu hình kết nối.
   - Nhập IP Server và Cổng, bấm **Kết nối Server** để vi điều khiển thiết lập socket TCP.

---

## 3. NẠP FLASH FIRMWARE (.BIN) (TAB 3)
1. **Cấu hình chung:**
   - **Mục tiêu Chip:** Chọn chip mục tiêu (mặc định `auto` để esptool tự nhận diện).
   - **Tốc độ Nạp (Baud):** Khuyến nghị `460800` hoặc `921600` để nạp nhanh, hoặc `115200` nếu cáp truyền tín hiệu kém.
   - Tùy chọn **Xóa sạch Flash trước khi nạp (--erase-all)** nếu muốn format trắng bộ nhớ trước khi ghi.
2. **Danh sách File nạp:**
   - Hỗ trợ nạp tối đa 4 file binary (.bin) cùng lúc.
   - Bấm **Chọn File...** để duyệt tìm file `.bin` trên máy tính.
   - Điền địa chỉ **Offset** nạp tương ứng (ví dụ: `0x1000` cho Bootloader, `0x8000` cho Partitions, `0xe000` cho Boot App0, `0x10000` cho Firmware ứng dụng).
   - Tích chọn ô kích hoạt cho các file muốn nạp.
   - Ứng dụng tự động kiểm tra tính hợp lệ và cảnh báo nếu có xung đột hoặc chồng lấn vùng nhớ.
3. **Bắt đầu nạp:**
   - Bấm nút **BẮT ĐẦU NẠP FLASH**.
   - Theo dõi thanh tiến trình phần trăm (%) và log chi tiết thời gian thực.
4. **Công cụ Xóa Flash:**
   - **Xóa Toàn Bộ Flash:** Xóa sạch toàn bộ bộ nhớ flash vật lý của chip.
   - **Xóa vùng Flash:** Xóa một vùng cụ thể theo Offset và kích thước xác định (yêu cầu địa chỉ và độ dài chia hết cho sector 4 KB = 0x1000).

---

## 4. CÀI ĐẶT HỆ THỐNG
- Bấm nút **Cài đặt** ở góc trên bên phải để mở hộp thoại:
  - **Cài đặt chung:** Chuyển đổi giao diện Sáng / Tối, quản lý danh sách các cổng COM muốn ẩn/bỏ qua, thiết lập IP/Cổng TCP mặc định.
  - **Nút chức năng:** Tùy biến nhãn và lệnh cho 15 nút F1 -> F15.
  - **Hướng dẫn sử dụng & Giới thiệu:** Xem hướng dẫn tích hợp và thông tin phiên bản.
  - **Khôi phục gốc:** Đưa mọi cài đặt về mặc định ban đầu của phần mềm.
