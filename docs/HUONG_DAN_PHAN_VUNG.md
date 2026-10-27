# HƯỚNG DẪN QUẢN LÝ PHÂN VÙNG BỘ NHỚ FLASH ESP32 (PARTITION WIZARD)

> [!NOTE]
> Từ phiên bản **Esp32 tool v2.1**, công cụ **Partition Wizard** đã được tích hợp trực tiếp vào **Tab thứ 4** (ngay sau Tab Nạp Flash). Cung cấp giao diện trực quan phong cách MiniTool Partition Wizard, tự động tính toán Offset và biên dịch bảng phân vùng nhị phân 32-byte kèm MD5 Checksum tương thích 100% chuẩn ESP-IDF.

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

1. **Sơ Đồ Thanh Ổ Đĩa Trực Quan (MiniTool Disk Map):**
   - Vẽ trực quan các khối phân vùng theo tỷ lệ dung lượng thực tế của chip Flash.
   - Hiển thị rõ các vùng hệ thống (Bootloader, Partition Table), các phân vùng ứng dụng (Factory, OTA), phân vùng dữ liệu và các khoảng trống chưa phân bổ (*Unallocated Gaps*).
   - Hỗ trợ xem thông tin chi tiết qua Tooltip khi di chuột, nhấp chọn phân vùng tương ứng trong bảng, hoặc nhấp vào vùng trống để tạo ngay phân vùng mới.
   - Menu chuột phải tiện lợi trên sơ đồ: Chỉnh sửa, Xóa, Sao lưu (Dump), Xóa trắng (Erase) hoặc Nạp trực tiếp file `.bin`.

2. **Tự Động Dồn & Căn Lề Biên 4KB / 64KB (`Auto-Pack`):**
   - Chỉ với 1 nút bấm `⚡ Dồn & Căn 4K/64K`, công cụ tự động tính toán lại toàn bộ Offset nối tiếp nhau, đảm bảo không có phân vùng nào bị chồng lấn và tuân thủ tuyệt đối quy tắc căn biên của ESP-IDF.

3. **Kiểm Tra Hợp Lệ Thời Gian Thực (Rule Validator):**
   - Tự động phát hiện và cảnh báo: trùng tên, tên quá 16 bytes, phân vùng App đặt dưới 0x10000, Offset không chia hết cho 64KB/4KB, thiếu phân vùng `otadata` khi có khe `ota_X`, hoặc tổng dung lượng vượt quá kích thước chip Flash.

4. **Bộ Quy Đổi Đơn Vị Nhanh:**
   - Cho phép nhập tự do các định dạng như `64K`, `1M`, `1.5M`, `0x10000`, `65536` và tự động quy đổi tức thì ra Bytes, KB, MB, Hex và số lượng Sectors (4KB).

5. **Xuất / Nhập & Biên Dịch Đa Định Dạng:**
   - Đọc và xuất file `partitions.csv` chuẩn ESP-IDF.
   - Biên dịch trực tiếp bảng phân vùng sang file nhị phân `partition-table.bin` 32-byte struct kèm MD5 Checksum mà không cần cài đặt Python ESP-IDF `gen_esp32part.py`.
   - Quét tự động thư mục dự án ESP-IDF / PlatformIO để trích xuất cấu hình và kích thước file `.bin` thực tế.

6. **Thao Tác Phần Cứng Trực Tiếp Qua Chip:**
   - Đọc bảng phân vùng từ chip qua cổng COM.
   - Nạp bảng phân vùng mới xuống địa chỉ `0x8000` của chip.
   - Sao lưu (Dump) một phân vùng bất kỳ ra file `.bin`.
   - Xóa trắng (Erase Region) phân vùng trên chip.
   - Nạp file binary vào đúng Offset của phân vùng đang chọn.
   - Cơ chế bảo vệ xung đột: Tự động tạm ngắt Serial Monitor an toàn khi thực thi tác vụ esptool và phục hồi sau khi hoàn tất.
