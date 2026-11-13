# HƯỚNG DẪN QUẢN LÝ PHÂN VÙNG (ESP32 PARTITION WIZARD - v1.10)

Tab **Phân vùng** tích hợp bộ biên soạn & chẩn đoán phân vùng Flash ESP32 theo chuẩn **ESP-IDF (`gen_esp32part.py`)** với sơ đồ trực quan phong cách MiniTool Partition Wizard.

---

## 1. KHỞI TẠO & CẤU HÌNH DÒNG CHIP

- **Trạng thái khởi đầu trống:** Khi vừa mở ứng dụng, bảng phân vùng và sơ đồ thanh ổ đĩa được giữ trống hoàn toàn để tránh nhầm lẫn dữ liệu mẫu cũ với chip đang thao tác.
- **Chọn Chip tự chọn Flash cao nhất:** Khi chọn một dòng chip tại mục **Chip** (ví dụ `ESP32`, `ESP32-S3`, `ESP32-C3`, `ESP32-P4`), ứng dụng tự động cập nhật danh sách mức Flash hợp lệ của họ chip đó và tự chọn dung lượng **Flash lớn nhất** hỗ trợ; khi mở tệp CSV/BIN hoặc đọc từ chip, hộp chọn **Flash** cũng tự đồng bộ theo tổng dung lượng của bảng.
- **Thanh công cụ Responsive & Nút gọn:** Các nhóm nút công cụ trên đầu trang tự xuống dòng thông minh khi thu hẹp cửa sổ; nút **Hướng dẫn**, **Hoàn tác** và **Làm lại** hiển thị biểu tượng SVG sắc nét kèm chú giải (`tooltip`).
- **Đơn vị hiển thị:** Chuyển đổi qua lại giữa **Thập phân (KB/MB)** và **Thập lục phân (Hex)** tức thì.
- **Tự căn 4K/64K (`Auto-Align`):** Khi bật, ứng dụng tự căn lề mỗi phân vùng theo sector vật lý:
  - Phân vùng `app` (`factory`, `ota_0`, `ota_1`, `test`,...): Bắt buộc căn lề bội số **64 KB (`0x10000`)**.
  - Phân vùng `data` (`nvs`, `otadata`, `phy_init`, `spiffs`, `littlefs`, `fat`,...): Bắt buộc căn lề bội số **4 KB (`0x1000`)**.

---

## 2. THANH CÔNG CỤ NHẬP, THIẾT KẾ VÀ LƯU TỆP

- **Mẫu Chuẩn...:** Mở hộp thoại chọn mẫu chuẩn theo kịch bản thực tế (Minimal Factory, Dual OTA, LittleFS + OTA, AI/HMI 8MB-32MB,...).
- **Quét Dự Án:** Quét thư mục dự án (PlatformIO, ESP-IDF, Arduino) để đọc bảng phân vùng và đối chiếu tỷ lệ chiếm dụng thực tế của các tệp `.bin` đã build.
- **Mở CSV/BIN:** Đọc tệp `partitions.csv` hoặc tệp nhị phân bảng phân vùng chuẩn ESP-IDF `.bin` (hỗ trợ kiểm tra Magic Bytes `0xAA50` và `MD5`).
- **Lưu CSV:** Lưu toàn bộ bảng phân vùng hiện có dưới định dạng `.csv` chuẩn ESP-IDF:
  - Nếu bảng đang gắn với một tệp `.csv` đã mở/lưu trước đó, nhấn **Lưu CSV** sẽ lưu đè trực tiếp toàn bộ bảng vào tệp đó.
  - Nếu là bảng mới tạo hoặc mở từ `.bin` / đọc từ chip, ứng dụng mở hộp thoại **Lưu file CSV bảng phân vùng** để chọn nơi lưu.
- **Dồn và Căn 4K/64K:** Xếp khít toàn bộ bảng phân vùng theo chuẩn căn lề của ESP-IDF mà không chồng lấn.
- **Hoàn tác / Làm lại:** Hỗ trợ lịch sử chỉnh sửa trong phiên (`Undo` / `Redo`).

---

## 3. SƠ ĐỒ THANH Ổ ĐĨA & CHỈNH SỬA DÒNG

- **Sơ đồ MiniTool Partition Map:** Hiển thị vùng hệ thống (`Bootloader`, `Partition Table`), các phân vùng người dùng theo màu sắc phân loại (`app`, `nvs`, `phy`, `spiffs`/`fat`,...) và phần dung lượng còn trống (`Unallocated`). Khối đang được chọn có khung viền đôi độ tương phản cao đầy đủ trên cả nền Sáng và nền Tối.
- **Kéo chỉnh ranh giới trực quan:** Kéo biên phân vùng trực tiếp trên thanh Disk Map hoặc nhấp đúp chuột để sửa kích thước.
- **Nút `+ Thêm dòng`:**
  - Thêm một phân vùng mới nằm **ngay dưới (ngay sau)** phân vùng đang chọn trên bảng (hoặc ở cuối bảng nếu chưa chọn dòng nào).
  - Tự động gợi ý tên mới duy nhất không trùng lặp và tự động dịch chuyển hợp lệ nếu cần căn lề vùng phía sau.
- **Sửa dòng / Xóa dòng / Xóa tất cả:** Cho phép điều chỉnh chi tiết từng phân vùng hoặc làm sạch bảng nhanh chóng.

---

## 4. THAO TÁC PHẦN CỨNG TRỰC TIẾP VỚI CHIP ESP32

Mọi tác vụ phần cứng sử dụng chung thanh tiến trình ở đáy màn hình kèm tên tác vụ và ghi nhật ký chi tiết tại khung thu gọn **Nhật Ký Thao Tác Phần Cứng Phân Vùng**:

1. **Đọc bảng từ Chip:** Đọc vùng bảng phân vùng tại `0x8000` (tự nhận diện vùng `0x10000` khi bootloader cần mở rộng trên S3/P4 nếu có), giải mã chuẩn ESP-IDF và hiển thị lên cả Disk Map lẫn bảng chi tiết (kết quả thông báo gọn trên thanh trạng thái đáy và nhật ký, không bật hộp thoại chặn thao tác).
2. **Nạp bảng vào Chip:** Biên dịch bảng hiện tại sang nhị phân 3 KB kèm chữ ký `MD5` ở 32 byte cuối và nạp vào Flash qua `esptool`.
3. **Dump vùng:** Sao lưu dữ liệu nhị phân thực tế của đúng phân vùng đang chọn thành file `.bin`.
4. **Ghi vùng:** Nạp một file `.bin` (như `spiffs.bin`, `littlefs.bin`, `app.bin`, `nvs.bin`) vào đúng địa chỉ Offset của phân vùng đang chọn (kiểm tra dung lượng không vượt quá kích thước phân vùng).
5. **Xóa vùng:** Xóa trắng dải địa chỉ của riêng phân vùng đang chọn với địa chỉ & độ dài đã được căn lề sector 4 KB an toàn.
