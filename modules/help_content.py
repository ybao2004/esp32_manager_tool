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

- Kiểm tra & chẩn đoán chi tiết chip, Silicon Revision, Crystal, MAC (Station/AP/Bluetooth), dung lượng Flash & PSRAM, vùng nhớ RAM nội cấp phát (Heap), đối soát OUI Espressif kèm ghi chú nguồn gốc ngay dưới dòng OUI.
- Serial Monitor & Log gồm 2 sub-tab: Serial (thời gian thực, tự động cuộn, thêm timestamp, {len(CONTROL_CONFIG)} phím điều khiển IoT tùy biến nhãn/lệnh, Wi-Fi/TCP) và Log (nhật ký tập trung gắn tiền tố tên tab từ Tab 1, Tab 3, Tab 4, Tab 5).
- Nạp Flash đồng thời tối đa 4 file .bin với offset tùy chọn, xóa toàn bộ Flash và thanh tiến trình thống nhất ở đáy màn hình (0% -> 100%) kèm tên tiến trình, kiểm tra chồng lấn địa chỉ.
- Quản lý Phân vùng Bộ nhớ (ESP32 Partition Wizard): thanh công cụ gọn 1 hàng, nút Đọc từ chip đặt ngay cạnh Đơn vị, sơ đồ trực quan DiskMap 42px căn giữa số liệu, tự căn biên 4K/64K, nút Mẫu, Quét Dự Án, Mở CSV/BIN và Lưu CSV.
- Sao lưu & Nhân bản Trực tiếp (Backup & Direct Multi-Board Clone): đọc sơ đồ phân vùng từ board gốc, đặt tên file sao lưu chuẩn hóa theo Chip, MAC gốc, tên phân vùng, Offset và thời gian; hỗ trợ đọc/xem/sửa NVS & Hex, xuất/nạp/xóa dữ liệu phân vùng Non-Firmware kèm Menu chuột phải đồng bộ giữa bảng và sơ đồ đĩa, khóa an toàn Bootloader & Firmware App.
- Giao diện thuần PyQt6 phong cách Kỹ thuật Chuyên sâu (Engineering Sáng / Tối), màn hình khởi động hiển thị logo, tiến độ từng bước & tối ưu nạp lazy `esptool`, chế độ Đơn thực thể (Single-Instance) và giải phóng an toàn mọi luồng/cổng/tiến trình con khi thoát.
- Tab 5 dùng chung Cổng COM trên cùng cho Board Gốc (tự loại khỏi danh sách Board Đích dạng gọn COMxx căn trái), giữ tốc độ Baudrate độc lập và hiển thị chuẩn xác tiến trình `esptool` v4/v5.
- Kiểm tra & tải bản cập nhật ngay trong trang Cài đặt (kèm chấm đỏ điều hướng khi có bản mới, tùy chọn tự kiểm tra khi khởi động mặc định tắt, và tự thay thế `.exe` an toàn qua thư mục tạm).
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

2. SERIAL MONITOR & LOG
- Sub-tab Serial: Bấm Kết nối, nhập chuỗi rồi Gửi. Enter gửi, Shift+Enter xuống dòng. Tùy chọn thêm \\r\\n áp dụng cho lệnh gửi đi. Xóa màn hình ở thanh trên xóa log Serial.
- Sub-tab Log: Tập trung log thao tác từ Tab 1 [Kiểm tra Chip], Tab 3 [Nạp Firmware], Tab 4 [Phân vùng], và Tab 5 [Sao lưu & Chép] kèm bộ lọc nguồn tab, dấu thời gian, Lưu Log (.txt) và Xóa Log.
Bảng điều khiển có {len(CONTROL_CONFIG)} nút, lấy nhãn/lệnh từ cấu hình. Có thể sửa trong Cài đặt -> Phím chức năng F1 - F15; cài đặt đã lưu được ưu tiên hơn mặc định.
Các lệnh mặc định hiện tại:
{commands}
Reset ESP gửi RESET và tạo xung DTR/RTS; khác với lệnh CMD_RESET mặc định của F3.

3. NẠP FLASH
Chọn đúng chip, COM, baudrate và tối đa 4 file .bin với offset tương ứng. Các nút Bắt đầu nạp, Xóa toàn bộ Flash và Xóa nhật ký nằm gọn trên thanh cấu hình phía trên; tiến trình phần trăm và tên tác vụ hiển thị đồng bộ ở thanh trạng thái đáy. (Thao tác đọc/sửa/xóa phân vùng dữ liệu riêng lẻ đã được chuyển sang Tab 5: Sao lưu & Chép.)

4. PHÂN VÙNG BỘ NHỚ (PARTITION WIZARD)
- Mặc định luôn hiển thị 2 phân vùng hệ thống đầu tiên (S1: bootloader, S2: partition_table - được khóa an toàn) trên bảng và sơ đồ đĩa cùng vùng trống Unallocated; khi bấm Đọc từ chip, ứng dụng tự động quét bảng phân vùng từ 0x8000 đến 0x20000 (hỗ trợ cả các mạch ESP-IDF v5/v6 đặt bảng tại 0xC000, 0xD000, 0x10000...).
- Toàn bộ cấu hình Chip, Flash, Đọc từ chip, Mẫu, Quét Dự Án, Mở CSV/BIN, Lưu CSV và Hoàn tác / Làm lại nằm gọn trên 1 hàng ngang.
- Tùy chọn "Tự căn 4K/64K" và chế độ Đơn vị hiển thị (Thập phân / Hệ HEX / Song song dùng chung cho cả Tab 4 & Tab 5) được cấu hình tập trung trong trang Cài đặt.
- Hàng nút bên dưới tập trung vào biên tập cấu trúc bảng: + Thêm dòng, Sửa dòng, Xóa dòng và Xóa tất cả.

5. SAO LƯU & NHÂN BẢN (BACKUP / DIRECT CLONE)
- Toàn bộ nút cấu hình nguồn & lọc nhanh nằm gọn trên 1 hàng; Board Gốc dùng chung Cổng COM ở thanh trên cùng và Baudrate của Tab 5 độc lập với thanh trên cùng.
- Danh sách phân vùng ban đầu trống cho tới khi bấm "Đọc chip nguồn" (tự quét bảng phân vùng 0x8000..0x20000 và đọc eFuse PSRAM); tích hoặc bỏ tích sao lưu bằng cách bấm vào hộp kiểm ở cột Chọn (hoặc phím Space).
- Chuột phải lên bất kỳ dòng nào trong bảng phân vùng hoặc trên sơ đồ DiskMap (hoặc dùng nút "Đọc/Sửa dữ liệu", "Xóa dữ liệu") để: Đọc/Xem & Sửa dữ liệu NVS Key-Value hoặc Hex/UTF-8 (tự phân trang 16KB), Xuất nhanh (.bin), Nạp file .bin ghi đè vùng hoặc Xóa dữ liệu vùng Non-Firmware (Bootloader, Partition Table và App được khóa an toàn). Dùng nút "Xóa toàn bộ Flash" ngay bên phải "Xóa dữ liệu" khi cần xóa sạch toàn bộ Flash trên Board Gốc.
- Tên file sao lưu chuẩn hóa: Full Flash `<chip>_<MAC>_Full - <yyyymmdd_hhmmss>.bin`; từng phân vùng `<chip>_<MAC>_<tên phân vùng>_<offset> - <yyyymmdd_hhmmss>.bin`.
- Nháy LED nhận diện Board Gốc (tùy chọn ẩn trong Cài đặt): khi bật và đang ở Tab 5, đổi Cổng COM trên cùng sẽ tự động nháy LED trong 5 giây (qua luồng UART TX không xung DTR/RTS) và hiện nút "Nháy LED".
- Sao chép trực tiếp (Direct Multi-Board Clone): Cắm đồng thời 1 board gốc (chọn ở cổng COM trên cùng) và nhiều board đích (COMxx); danh sách Board Đích tự động loại trừ cổng Board Gốc.

6. CÀI ĐẶT & CẬP NHẬT
Trong trang Cài đặt (gồm 4 sub-tab):
- Cài đặt Chung và Cổng COM: Chọn chế độ Engineering Sáng / Tối đồng bộ tức thì, lọc ẩn cổng COM Bluetooth và cổng Modem/USB điện thoại (mặc định bật) hoặc cổng tùy chọn, cấu hình IP/Port mặc định, Tự căn 4K/64K, Đơn vị hiển thị và tùy chọn ẩn nháy LED 5s ở Tab 5. Lưu cài đặt thông báo trực tiếp trên thanh trạng thái dưới cùng.
- Phím chức năng F1 - F15: Tùy biến nhãn và lệnh cho 15 nút điều khiển.
- Cập nhật Phần mềm: Kiểm tra phiên bản mới từ GitHub Releases ngay trong trang Cài đặt (hiển thị dấu chấm đỏ hướng dẫn khi có bản mới), xem Release Notes, tải và tự cập nhật trực tiếp không mở cửa sổ terminal phụ tại `{GITHUB_REPO}`.
- Giới thiệu: Hiển thị trực tiếp thông tin phiên bản, tác giả, giấy phép và 6 nhóm tính năng cốt lõi ngay trong trang Cài đặt."""
