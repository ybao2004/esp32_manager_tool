# HƯỚNG DẪN QUẢN LÝ PHÂN VÙNG BỘ NHỚ FLASH ESP32 (PARTITION WIZARD)

> [!NOTE]
> Trong **Esp32 manager tool (v1.3)**, công cụ **Partition Wizard** được tích hợp trực tiếp tại **Tab thứ 4** (ngay sau Tab Nạp Flash). Cung cấp giao diện trực quan phong cách MiniTool Partition Wizard, tự động tính toán Offset và biên dịch bảng phân vùng nhị phân 32-byte kèm MD5 Checksum tương thích 100% chuẩn ESP-IDF.

---

## 1. Kiến Trúc Bảng Phân Vùng (Partition Table)
Bảng phân vùng của ESP32 định nghĩa cách chia bộ nhớ Flash SPI thành các vùng nhớ chức năng riêng biệt:
- **Name:** Nhãn định danh của phân vùng (tối đa 16 bytes ASCII).
- **Type:** Kiểu phân vùng chính: `app` (mã chương trình thực thi) hoặc `data` (dữ liệu).
- **SubType:** Phân loại chi tiết chức năng:
  - Kiểu `app`: `factory`, `ota_0` -> `ota_15`, `test`.
  - Kiểu `data`: `nvs`, `phy`, `ota` (otadata), `spiffs`, `littlefs`, `fat`, `coredump`, `nvs_keys`, `efuse`.
- **Offset:** Địa chỉ bắt đầu trong bộ nhớ Flash (bắt buộc căn lề sector 64 KB = `0x10000` cho `app` và 4 KB = `0x1000` cho `data`).
- **Size:** Kích thước của phân vùng (bội số của sector 4 KB = `0x1000`).
- **Flags:** Cờ bổ sung: `encrypted` (mã hóa), `readonly` (chỉ đọc).

---

## 2. Các Tính Năng Nổi Bật của Tab Partition Wizard (Tab 4)

1. **Bố Cục Thanh Điều Khiển Tinh Giản:**
   - Hàng 1: Lựa chọn **Dòng Chip**, **Dung lượng Flash** và **Chế độ hiển thị số liệu** (Thập phân, Hex, Song song).
   - Hàng 2: Tích hợp trực tiếp các nút chức năng tinh gọn (loại bỏ icon gây rối mắt): `Dồn & Căn 4K/64K`, `Mẫu Chuẩn`, `Mở CSV / BIN`, `Xuất CSV`, `Xuất BIN`, `Quét Dự Án`, `Hoàn tác`, `Làm lại`.
   - Các nút Thêm/Sửa/Xóa thừa thãi trên thanh công cụ được loại bỏ để tập trung thao tác trực tiếp vào từng dòng trong bảng.

2. **Sơ Đồ Thanh Ổ Đĩa Trực Quan & Tooltip Tra Cứu Chuyên Sâu (MiniTool Disk Map):**
   - Biểu diễn trực quan tỷ lệ các phân vùng trên toàn bộ dung lượng chip Flash kèm vùng trống (*Unallocated Gaps*).
   - **Tooltip tra cứu chi tiết khi di chuột:** Hiển thị bảng thông tin kỹ thuật toàn diện cho từng phân vùng:
     - Tên, Kiểu, Phân loại, Offset, Dung lượng, Số sector vật lý (4KB) và quy tắc căn biên yêu cầu.
     - **📌 Mục đích sử dụng:** Giải thích công dụng thực tế của phân vùng (NVS lưu Wi-Fi/biến, OTA để nạp từ xa, LittleFS lưu web tĩnh, coredump ghi nhận lỗi crash...).
     - **💡 Khuyến nghị dung lượng:** Bảng hướng dẫn dung lượng tối thiểu, thông thường và tối đa phù hợp cho từng loại.
   - Nhấp chuột vào khoảng trống Unallocated để tạo ngay phân vùng mới vừa vặn trong khe trống đó.

3. **Bảng Phân Vùng Tương Tác Nhanh (Smart Interactive Table):**
   - **Cột Số Thứ Tự (`+ / -  STT`):**
     - Hiển thị trực tiếp các nút bấm nhanh: `[+] [-]  #1`, `[+] [-]  #2`,...
     - Nhấp chuột vào `[+]`: Tự động chèn ngay một phân vùng mới nối tiếp sau dòng đó (tự tính offset nối tiếp và căn lề).
     - Nhấp chuột vào `[-]`: Xác nhận và xóa phân vùng tương ứng.
     - Nhấp vào tiêu đề cột `+ / -  STT` để thêm nhanh phân vùng vào cuối bảng.
   - **Menu Chuột Phải Ngữ Cảnh Thông Minh (Smart Column Context Menu):**
     - Nhấp chuột phải vào từng cột cụ thể để mở menu thay đổi nhanh giá trị cho riêng cột đó:
       - **Cột Tên (Name):** Danh sách tên chuẩn phổ biến (`nvs`, `otadata`, `factory`, `ota_0`, `storage`, `littlefs`,...), tùy chọn `✏️ Tự đặt tên...` và `(Chưa đặt tên / Trống)`.
       - **Cột Kiểu (Type):** Đổi nhanh giữa `app` và `data` (tự động gợi ý subtype tương thích).
       - **Cột Phân loại (SubType):** Danh sách subtype chuẩn phù hợp theo Kiểu App hoặc Data, kèm tùy chọn `✏️ Tự đặt SubType...`.
       - **Cột Offset:** Nút `⚡ Tự động tính toán (Dồn nối tiếp dòng trước)`, các mốc Offset thông dụng và `✏️ Tự nhập Offset...`.
       - **Cột Dung lượng (Size):** Danh sách các mốc dung lượng dựng sẵn (4KB, 16KB, 64KB, 1MB, 1.5MB, 2MB, 3MB...) và `✏️ Tự nhập dung lượng...` (hỗ trợ nhập `64K`, `1M`, `0x10000`).
       - **Cột Cờ (Flags):** Bật/tắt nhanh cờ `encrypted` (mã hóa), `readonly` (chỉ đọc) hoặc `(Không có / Trống)`.
     - Phía dưới menu ngữ cảnh của mọi cột đều tích hợp các tác vụ: Sao lưu (Dump), Xóa trắng (Erase Region), Nạp file `.bin` và Xóa phân vùng.

4. **Tự Động Dồn & Căn Lề Biên 4KB / 64KB (`Dồn & Căn 4K/64K`):**
   - Tự động tính toán lại toàn bộ Offset nối tiếp nhau, đảm bảo không có phân vùng nào bị chồng lấn và tuân thủ tuyệt đối quy tắc căn biên của ESP-IDF (App căn 64KB, Data căn 4KB).

5. **Kiểm Tra Hợp Lệ Thời Gian Thực (Rule Validator):**
   - Tự động phát hiện và cảnh báo: trùng tên, tên quá 16 bytes, phân vùng App đặt dưới 0x10000, Offset không chia hết cho 64KB/4KB, thiếu phân vùng `otadata` khi có khe `ota_X`, hoặc tổng dung lượng vượt quá kích thước chip Flash.

6. **Xuất / Nhập & Biên Dịch Đa Định Dạng:**
   - Đọc và xuất file `partitions.csv` chuẩn ESP-IDF.
   - Biên dịch trực tiếp bảng phân vùng sang file nhị phân `partition-table.bin` 32-byte struct kèm MD5 Checksum.
   - Quét tự động thư mục dự án ESP-IDF / PlatformIO để trích xuất cấu hình và kích thước file `.bin` thực tế.

7. **Thao Tác Phần Cứng Trực Tiếp Qua Chip:**
   - Đọc bảng phân vùng từ chip qua cổng COM.
   - Nạp bảng phân vùng mới xuống địa chỉ `0x8000` của chip.
   - Sao lưu (Dump) một phân vùng bất kỳ ra file `.bin`.
   - Xóa trắng (Erase Region) phân vùng trên chip.
   - Nạp file binary vào đúng Offset của phân vùng đang chọn.
   - Cơ chế bảo vệ xung đột: Tự động tạm ngắt Serial Monitor an toàn khi thực thi tác vụ esptool và phục hồi sau khi hoàn tất.
