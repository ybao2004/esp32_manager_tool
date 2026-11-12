"""Current in-app product description and quick-start instructions."""
from modules.config import CONTROL_CONFIG, APP_NAME, APP_VERSION, APP_AUTHOR, APP_LICENSE, GITHUB_REPO


def quick_start_text():
    commands = '\n'.join(f"  F{key}: {label} -> {command}" for key, (label, command) in sorted(CONTROL_CONFIG.items()))
    return f"""HƯỚNG DẪN SỬ DỤNG {APP_NAME.upper()} (v{APP_VERSION})
Tác giả: {APP_AUTHOR} | Bản quyền: {APP_LICENSE} License

KHỞI CHẠY
Chạy main.py hoặc file EXE đã đóng gói. modules/config.py chỉ chứa cấu hình, không phải điểm khởi chạy.

1. KIỂM TRA PHẦN CỨNG
Chọn COM và baudrate, bấm KIỂM TRA TOÀN DIỆN. Đọc báo cáo, xem Output Thô hoặc Lưu Báo Cáo. Thông tin nhận được phụ thuộc chip và công cụ; đối soát OUI MAC không phải chứng nhận chip chính hãng.

2. SERIAL MONITOR & ĐIỀU KHIỂN
Bấm Kết nối, nhập chuỗi rồi Gửi. Enter gửi, Shift+Enter xuống dòng. Tùy chọn thêm \\r\\n áp dụng cho lệnh gửi đi. Xóa màn hình ở thanh trên xóa log Serial.
Bảng điều khiển có {len(CONTROL_CONFIG)} nút, lấy nhãn/lệnh từ cấu hình. Có thể sửa trong Cài đặt -> Nút chức năng; cài đặt đã lưu được ưu tiên hơn mặc định.
Các lệnh mặc định hiện tại:
{commands}
Reset ESP gửi RESET và tạo xung DTR/RTS; khác với lệnh CMD_RESET mặc định của F3.

3. NẠP FLASH
Chọn đúng chip, COM, tốc độ và tối đa 4 file .bin với offset tương ứng. Kiểm tra file và địa chỉ trước khi nạp.
Xóa Toàn Bộ Flash xóa cả chương trình và dữ liệu. Xóa vùng Flash chỉ dùng dải địa chỉ bạn nhập.

4. PHÂN VÙNG BỘ NHỚ (PARTITION WIZARD)
Sơ đồ thanh ổ đĩa trực quan phong cách MiniTool, tự động tính toán và hiển thị phân vùng chuẩn ESP-IDF.
Thao tác thêm, sửa, xóa, dồn biên tự động 4KB/64KB và nạp mẫu preset.
Hỗ trợ đọc/xuất file CSV (partitions.csv), biên dịch nhị phân (partition-table.bin) kèm MD5 Checksum.
Thao tác phần cứng an toàn: Đọc từ chip, nạp xuống chip, sao lưu (dump), xóa trắng (erase) và nạp file .bin trực tiếp vào từng phân vùng.

5. SAO LƯU & NHÂN BẢN (BACKUP / DIRECT CLONE)
- Thanh phân vùng trực quan (Disk Map) hiển thị đầy đủ từ Bootloader, Partition Table đến các phân vùng ứng dụng và dữ liệu.
- Tích chọn từng phân vùng hoặc tất cả phân vùng để sao lưu, tự động cắt bỏ vùng trống 0xFF cuối phân vùng (Smart Trim) và sinh hồ sơ sao lưu đầy đủ (backup_info.txt, backup_manifest.json, partitions.csv) ghi lại SHA-256, MD5, dung lượng, địa chỉ offset, thời gian, loại chip và MAC gốc.
- Sao chép trực tiếp (Direct Multi-Board Clone): Cắm đồng thời 1 board gốc và 1 hoặc nhiều board đích để nhân bản trực tiếp sang tất cả board đích chỉ với 1 cú nhấp chuột (mặc định bỏ qua NVS/otadata để tránh nhân bản nhầm khóa định danh riêng).

6. CÀI ĐẶT & CẬP NHẬT
Trong Cài đặt:
- Cài đặt chung: Tùy chỉnh giao diện Sáng/Tối, lọc ẩn cổng COM Bluetooth hoặc cổng tùy chọn, cấu hình IP/Port server mặc định.
- Nút chức năng: Tùy biến nhãn và lệnh cho 15 nút điều khiển.
- Cập nhật (Update): Kiểm tra phiên bản mới nhất từ kho GitHub https://github.com/{GITHUB_REPO} và tải trực tiếp file cập nhật về máy.
Tài liệu chi tiết đi kèm dự án nằm trong thư mục docs/."""


def about_features_text():
    return f"""Công cụ toàn diện dành cho họ chip Espressif: kiểm tra phần cứng chuyên sâu, theo dõi Serial, nạp Flash Firmware, quản lý phân vùng bộ nhớ (Partition Wizard), sao lưu & nhân bản trực tiếp nhiều board (Backup & Direct Clone).
Tác giả: {APP_AUTHOR}  |  Bản quyền: GNU General Public License v3.0 ({APP_LICENSE})

- Kiểm tra & chẩn đoán chi tiết chip, Silicon Revision, Crystal, MAC (Station/AP/Bluetooth), dung lượng Flash & PSRAM, vùng nhớ RAM nội cấp phát (Heap), đối soát OUI Espressif.
- Serial Monitor thời gian thực, tự động cuộn, thêm timestamp, {len(CONTROL_CONFIG)} phím điều khiển IoT tùy biến nhãn/lệnh và điều khiển Wi-Fi/TCP.
- Nạp Flash đồng thời tối đa 4 file .bin với offset tùy chọn, thanh tiến trình phần trăm thời gian thực (0% -> 100%), kiểm tra chồng lấn địa chỉ.
- Quản lý Phân vùng Bộ nhớ (ESP32 Partition Wizard): sơ đồ trực quan MiniTool, tự động dồn biên 4K/64K, xuất/nhập CSV và nhị phân MD5, đọc/nạp/dump/erase qua chip.
- Sao lưu & Nhân bản Trực tiếp (Backup & Direct Multi-Board Clone): đọc sơ đồ phân vùng từ board gốc, sao lưu từng vùng hoặc toàn bộ kèm hồ sơ băm SHA-256 / MD5 / MAC gốc, và nhân bản trực tiếp từ 1 board gốc sang nhiều board đích cùng lúc.
- Tự động Kiểm tra & Tải Cập nhật: Tích hợp kết nối GitHub Releases API, tải trực tiếp file cập nhật kèm thanh tiến trình download thời gian thực.
- Giao diện PyQt6 hiện đại với thanh điều hướng dọc (Sidebar) có thể thu gọn/mở rộng, biểu tượng Vector QPainter sắc nét, hỗ trợ Sáng / Tối đồng bộ qua QSS.
- Nền tảng: Python, PyQt6, esptool, PySerial."""
