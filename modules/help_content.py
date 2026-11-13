# -*- coding: utf-8 -*-
"""Nội dung hướng dẫn nhanh và giới thiệu cho ESP32 Manager Tool."""

from modules.config import (
    APP_NAME,
    APP_VERSION,
    APP_AUTHOR,
    APP_LICENSE,
    GITHUB_REPO,
    CONTROL_CONFIG,
)


def about_features_text():
    return f"""Công cụ toàn diện dành cho họ chip Espressif: kiểm tra phần cứng chuyên sâu, theo dõi Serial, nạp Flash Firmware, quản lý phân vùng bộ nhớ (Partition Wizard), sao lưu & nhân bản trực tiếp nhiều board (Backup & Direct Clone).
Tác giả: {APP_AUTHOR}  |  Bản quyền: GNU General Public License v3.0 ({APP_LICENSE})

- Kiểm tra & chẩn đoán chi tiết chip, Silicon Revision, Crystal, MAC (Station/AP/Bluetooth), dung lượng Flash & PSRAM, vùng nhớ RAM nội cấp phát (Heap), đối soát OUI Espressif.
- Serial Monitor thời gian thực, tự động cuộn, thêm timestamp, {len(CONTROL_CONFIG)} phím điều khiển IoT tùy biến nhãn/lệnh và điều khiển Wi-Fi/TCP.
- Nạp Flash đồng thời tối đa 4 file .bin với offset tùy chọn, thanh tiến trình thống nhất ở đáy màn hình (0% -> 100%) kèm tên tiến trình, kiểm tra chồng lấn địa chỉ.
- Quản lý Phân vùng Bộ nhớ (ESP32 Partition Wizard): sơ đồ trực quan MiniTool, chọn chip tự đặt dung lượng Flash tối đa hỗ trợ, tự động dồn biên 4K/64K, chèn phân vùng ngay sau dòng đang chọn, mở CSV/BIN và lưu toàn bảng ra CSV (Lưu CSV), đọc/nạp/dump/erase qua chip.
- Sao lưu & Nhân bản Trực tiếp (Backup & Direct Multi-Board Clone): đọc sơ đồ phân vùng từ board gốc, sao lưu từng vùng hoặc toàn bộ kèm hồ sơ băm SHA-256 / MD5 / MAC gốc, hỗ trợ tùy chọn nháy LED 5 giây nhận diện Board Gốc tại Tab 5, và nhân bản trực tiếp từ 1 board gốc sang nhiều board đích cùng lúc.
- Tự động Kiểm tra & Tải Cập nhật: Tích hợp kết nối GitHub Releases API, tải trực tiếp file cập nhật kèm thanh tiến trình download thời gian thực.
- Giao diện thuần PyQt6 phong cách Kỹ thuật Chuyên sâu (Engineering Sáng / Tối), biểu tượng Vector QSvgRenderer tự đổi màu theo chủ đề và icon chuẩn trên thanh tác vụ Windows.
- Nền tảng: Python, PyQt6, esptool, PySerial."""


def quick_start_text():
    commands = "\n".join(
        f"  F{key}: {label} -> {command}"
        for key, (label, command) in sorted(CONTROL_CONFIG.items())
    )
    return f"""HƯỚNG DẪN SỬ DỤNG {APP_NAME.upper()} (v{APP_VERSION})
Tác giả: {APP_AUTHOR} | Bản quyền: {APP_LICENSE} License

KHỞI CHẠY
Chạy main.py hoặc file EXE đã đóng gói. modules/config.py chỉ chứa cấu hình, không phải điểm khởi chạy.

1. KIỂM TRA PHẦN CỨNG
Chọn COM và baudrate, bấm "Kiểm tra Chip". Đọc báo cáo liền mạch hoặc bảng thông số, xem log thô esptool hoặc Lưu Báo Cáo. Thanh tiến trình dưới đáy hiển thị trạng thái thực thi của tiến trình hiện tại.

2. SERIAL MONITOR & ĐIỀU KHIỂN
Bấm Kết nối, nhập chuỗi rồi Gửi. Enter gửi, Shift+Enter xuống dòng. Tùy chọn thêm \\r\\n áp dụng cho lệnh gửi đi. Xóa màn hình ở thanh trên xóa log Serial.
Bảng điều khiển có {len(CONTROL_CONFIG)} nút, lấy nhãn/lệnh từ cấu hình. Có thể sửa trong Cài đặt -> Phím chức năng F1 - F15; cài đặt đã lưu được ưu tiên hơn mặc định.
Các lệnh mặc định hiện tại:
{commands}
Reset ESP gửi RESET và tạo xung DTR/RTS; khác với lệnh CMD_RESET mặc định của F3.

3. NẠP FLASH
Chọn đúng chip, COM, baudrate và tối đa 4 file .bin với offset tương ứng. Các nút Bắt đầu nạp, Xóa vùng nhớ, Xóa toàn bộ Flash và Xóa nhật ký nằm gọn trên thanh cấu hình phía trên; tiến trình phần trăm và tên tác vụ hiển thị đồng bộ ở thanh trạng thái đáy.

4. PHÂN VÙNG BỘ NHỚ (PARTITION WIZARD)
- Ban đầu bảng và sơ đồ đĩa trống hoàn toàn cho tới khi bạn chọn Mẫu Chuẩn..., Quét Dự Án, Mở CSV/BIN, Đọc bảng từ Chip hoặc bấm + Thêm dòng.
- Chọn dòng chip sẽ tự động cập nhật danh sách Flash tương thích và chọn dung lượng Flash cao nhất của chip đó.
- Nút "+ Thêm dòng" chèn phân vùng mới ngay sau phân vùng đang chọn và tự tránh trùng tên.
- Nút "Lưu CSV" lưu toàn bộ bảng phân vùng ra tệp .csv chuẩn ESP-IDF (tự lưu đè nếu đang mở từ .csv hoặc mở hộp thoại chọn nơi lưu).
- Thao tác phần cứng an toàn: Đọc bảng từ Chip, Nạp bảng vào Chip, Dump vùng, Ghi vùng và Xóa vùng với nhật ký thu gọn và tiến trình hiển thị ở thanh trạng thái đáy.

5. SAO LƯU & NHÂN BẢN (BACKUP / DIRECT CLONE)
- Ban đầu danh sách phân vùng trống cho tới khi đọc cấu trúc từ Board Gốc.
- Tích chọn từng phân vùng hoặc tất cả phân vùng để sao lưu, tự động cắt bỏ vùng trống 0xFF cuối phân vùng và sinh hồ sơ sao lưu đầy đủ (backup_info.txt, backup_manifest.json, partitions.csv) ghi lại SHA-256, MD5, offset, kích thước, chip và MAC gốc.
- Nháy LED nhận diện Board Gốc (tùy chọn nâng cao trong Cài đặt): khi bật và đang ở Tab 5, chọn Board Gốc sẽ tự động nháy LED trong 5 giây (qua luồng UART TX không xung DTR/RTS) và hiện nút "Nháy LED" ngay cạnh ô chọn cổng nguồn.
- Sao chép trực tiếp (Direct Multi-Board Clone): Cắm đồng thời 1 board gốc và 1 hoặc nhiều board đích để nhân bản trực tiếp sang tất cả board đích.

6. CÀI ĐẶT & CẬP NHẬT
Trong trang Cài đặt:
- Cài đặt Chung và Cổng COM: Chọn chế độ Engineering Sáng / Tối đồng bộ tức thì, lọc ẩn cổng COM Bluetooth hoặc cổng tùy chọn, cấu hình IP/Port mặc định, và bật/tắt tùy chọn ẩn nháy LED 5s ở Tab 5.
- Phím chức năng F1 - F15: Tùy biến nhãn và lệnh cho 15 nút điều khiển.
- Kiểm Tra Cập Nhật: Kiểm tra phiên bản mới nhất từ kho GitHub https://github.com/{GITHUB_REPO} và tải trực tiếp file cập nhật về máy.
Tài liệu chi tiết đi kèm dự án nằm trong thư mục docs/."""
