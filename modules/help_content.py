"""Current in-app product description and quick-start instructions."""
from modules.config import CONTROL_CONFIG, APP_NAME, APP_VERSION, GITHUB_REPO


def quick_start_text():
    commands = '\n'.join(f"  F{key}: {label} → {command}" for key, (label, command) in sorted(CONTROL_CONFIG.items()))
    return f"""HƯỚNG DẪN SỬ DỤNG {APP_NAME.upper()} (v{APP_VERSION})

KHỞI CHẠY
Chạy main.py hoặc file EXE đã đóng gói. modules/config.py chỉ chứa cấu hình, không phải điểm khởi chạy.

1. KIỂM TRA PHẦN CỨNG
Chọn COM và baudrate, bấm KIỂM TRA TOÀN DIỆN. Đọc báo cáo, xem Output Thô hoặc Lưu Báo Cáo. Thông tin nhận được phụ thuộc chip và công cụ; đối soát OUI MAC không phải chứng nhận chip chính hãng.

2. SERIAL MONITOR & ĐIỀU KHIỂN
Bấm Kết nối, nhập chuỗi rồi Gửi. Enter gửi, Shift+Enter xuống dòng. Tùy chọn thêm \\r\\n áp dụng cho lệnh gửi đi. Xóa màn hình ở thanh trên xóa log Serial.
Bảng điều khiển có {len(CONTROL_CONFIG)} nút, lấy nhãn/lệnh từ cấu hình. Có thể sửa trong Cài đặt → Nút chức năng; cài đặt đã lưu được ưu tiên hơn mặc định.
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

5. CÀI ĐẶT & CẬP NHẬT
Trong Cài đặt:
- Cài đặt chung: Tùy chỉnh giao diện Sáng/Tối, lọc ẩn cổng COM, cấu hình IP/Port server mặc định.
- Nút chức năng: Tùy biến nhãn và lệnh cho 15 nút điều khiển.
- Cập nhật (Update): Kiểm tra phiên bản mới nhất từ kho GitHub https://github.com/{GITHUB_REPO} và tải trực tiếp file cập nhật về máy.
Tài liệu chi tiết đi kèm dự án nằm trong thư mục docs/."""


def about_features_text():
    return f"""Công cụ toàn diện dành cho họ chip Espressif: kiểm tra phần cứng, theo dõi Serial, nạp Flash Firmware, quản lý phân vùng bộ nhớ (Partition Wizard) và kiểm tra cập nhật tự động.

• Kiểm tra & chẩn đoán chi tiết chip, Silicon Revision, Crystal, MAC (Station/AP/Bluetooth), dung lượng Flash & PSRAM, đối soát OUI Espressif.
• Serial Monitor thời gian thực, tự động cuộn, thêm timestamp, {len(CONTROL_CONFIG)} phím điều khiển IoT tùy biến nhãn/lệnh và điều khiển Wi-Fi/TCP.
• Nạp Flash đồng thời tối đa 4 file .bin với offset tùy chọn, thanh tiến trình thời gian thực, kiểm tra chồng lấn địa chỉ.
• Quản lý Phân vùng Bộ nhớ (ESP32 Partition Wizard): sơ đồ trực quan MiniTool, tự động dồn biên 4K/64K, xuất/nhập CSV và nhị phân MD5, đọc/nạp/dump/erase qua chip.
• Tự động Kiểm tra & Tải Cập nhật: Tích hợp kết nối GitHub Releases API, tải trực tiếp file cập nhật kèm thanh tiến trình download thời gian thực.
• Công cụ Xóa Toàn Bộ Flash và Xóa Vùng Flash theo địa chỉ căn lề sector 4 KB an toàn.
• Hỗ trợ giao diện Sáng / Tối, icon chuẩn High-DPI và chạy độc lập không phụ thuộc môi trường cài đặt ngoài.
• Nền tảng: Python, Tkinter, esptool, PySerial."""
