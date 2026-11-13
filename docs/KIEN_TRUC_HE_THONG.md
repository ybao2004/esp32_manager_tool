# KIẾN TRÚC HỆ THỐNG & THIẾT KẾ PHẦN MỀM (v1.10)

> Tài liệu mô tả kiến trúc thuần PyQt6 của **ESP32 Manager Tool v1.10**, cơ chế khởi động tối ưu kèm màn hình `StartupSplash` thuần `QWidget` trên Taskbar, cập nhật nội tuyến trong Cài đặt kèm self-updater Windows, chuẩn tương phản WCAG AA, đơn thực thể và giải phóng tài nguyên an toàn.

---

## 1. TỔNG QUAN KIẾN TRÚC TỔNG THỂ

Từ phiên bản v1.7 trở đi (hiện tại v1.10), **ESP32 Manager Tool** chạy hoàn toàn trên **PyQt6** (đã loại bỏ 100% thư viện `tkinter` và `ttk`). Điểm vào `main.py` khởi tạo `QApplication` và kiểm tra đơn thực thể sớm, hiển thị ngay `StartupSplash` thuần `QWidget`, nạp lazy `MainWindow` cùng `esptool` để rút ngắn độ trễ hiển thị ban đầu, rồi vận hành `InspectorApp` (`modules/app_core.py`) với 5 lớp Mixin nghiệp vụ chuyên biệt:

```text
InspectorApp (modules/app_core.py)
 ├── MainWindow (modules/ui/main_window.py — QMainWindow, Sidebar, Stack 6 Trang, Unified Bottom ProgressBar)
 ├── InspectorTabMixin (modules/tabs/tab_inspector.py)
 ├── MonitorTabMixin (modules/tabs/tab_monitor.py)
 ├── FlasherTabMixin (modules/tabs/tab_flasher.py)
 ├── PartitionTabMixin (modules/tabs/tab_partition.py)
 └── BackupCloneTabMixin (modules/tabs/tab_backup_clone.py)
```

### Lợi ích của mô hình tách UI Page + Business Mixin
- **Tách biệt giao diện và xử lý phần cứng:** Lớp trang `modules/ui/pages/*.py` chỉ xây dựng widget PyQt6, ràng buộc sự kiện và cung cấp lớp tương thích (`_ComboCompat`, `_TreeCompat`,...) để các lớp Mixin nghiệp vụ gọi ổn định.
- **Dễ kiểm thử tự động không cần phần cứng thật:** Các kiểm thử trong `tests/` khởi tạo `InspectorApp` ở chế độ offscreen PyQt6 (`QT_QPA_PLATFORM=offscreen`) kết hợp bộ giả lập phần cứng (`tests/mock_hardware/`).

---

## 2. PHÂN HỆ GIAO DIỆN PYQT6 & HỆ THỐNG CHỦ ĐỀ (`modules/ui/`)

### 2.1. Theme Engine Engineering Sáng / Tối (`modules/ui/theme/`)
- `tokens.py`: Định nghĩa bảng màu **Kỹ thuật Chuyên sâu (`engineering`)** cho hai chế độ `light` và `dark`, kích thước bo góc, chữ viết monospace/UI, và ép mọi giá trị cấu hình theme cũ (nếu có) về `"engineering"`.
- `qss.py`: Sinh stylesheet QSS thống nhất toàn ứng dụng; loại bỏ viền xanh focus gây chói mắt quanh `QTableWidget`, `QLineEdit` ô F1-F15 và các combobox; hỗ trợ role `section_danger` và nâng độ tương phản mục Sidebar đang chọn trong Dark Mode (`#1D4ED8`).
- `manager.py`:
  - `EngineeringProxyStyle`: Lớp `QProxyStyle` tự vẽ trực tiếp vector cho `PE_IndicatorCheckBox` và `PE_IndicatorRadioButton` trên `QPainter` có khử răng cưa, bảo đảm hình vuông/tròn đầy đặn, không bị cắt mép ở mọi tỷ lệ DPI.
  - `ThemeManager` & `_WeakSignal`: Phát tín hiệu yếu an toàn mỗi khi chuyển giữa Engineering Sáng và Engineering Tối.
- `icons.py`: Bộ render biểu tượng vector từ `icons/fluent/*.svg` qua `QSvgRenderer` (bao gồm `arrow_undo.svg` / `arrow_redo.svg`), kèm hàm `bind_themed_icon(target, name, size, role)` hỗ trợ `text`, `muted`, `on_accent` và `danger`, tự động tô lại màu icon cho nút bấm và tiêu đề `Card` ngay khi đổi chế độ Sáng/Tối.

### 2.2. Hệ thống Widget Chuyên Dụng (`modules/ui/widgets/`)
- `flow_layout.py`: `FlowLayout` & helper `make_group` cho các thanh công cụ đa hàng trên 6 trang làm việc, tính lại `heightForWidth` chuẩn xác giúp cửa sổ thu gọn (`960x580`) tự cuống dòng không cắt xén widget.
- `sidebar.py`: Thanh điều hướng dọc thu gọn (`52px`) / mở rộng (`190px`).
- `card.py`: Khung thẻ với icon và tiêu đề (`section` / `section_danger`) đồng bộ hoàn toàn theo theme.
- `disk_map.py`: `DiskMapWidget` vẽ phân vùng tỷ lệ Flash theo 2 lượt với bảng màu đạt chuẩn tương phản WCAG 2.2 AA (>= 4.5:1) trên cả hai nền Sáng/Tối và khung viền chọn đôi tương phản cao.
- `log_view.py`: Gắn thuộc tính `_ROLE_PROP` cho từng đoạn văn bản log và tự động tô lại toàn bộ khối log đã hiển thị khi người dùng đổi Sáng/Tối.
- `splash.py`: `StartupSplash` thuần `QWidget` (QSS gradient, không dùng `QSplashScreen`/ảnh `pyi_splash`) hiển thị logo, tên app, thanh tiến độ và bước khởi tạo thực tế ngay trên Taskbar Windows (nằm ở lớp cửa sổ thường, không khóa luôn-trên-cùng và không tự đẩy xuống đáy Z-order).
- `update_badge.py`: `UpdateDotBadge` vẽ chấm đỏ hướng dẫn xuyên suốt Sidebar -> Tab Cài đặt -> nút cập nhật khi có phiên bản mới.
- `connection_bar.py`, `collapsible.py`, `key_value_table.py`, `info_bar.py`, `progress_row.py`.

### 2.3. Hệ thống Hộp thoại & Icon Cửa sổ / Taskbar
- `modules/ui/dialogs/` & `modules/ui/dialogs_service.py`: Hộp thoại thuần PyQt6 (`PartitionEditDialog`, `PresetDialog`, `SizeInputDialog`, `EraseRegionDialog`, `AboutDialog`, `UpdateDialog`).
- `modules/app_core.py` & `main.py`: Gọi `SetCurrentProcessExplicitAppUserModelID` của Windows Shell cùng Win32 `LoadImageW` + `WM_SETICON` (`set_window_icon_native`) để bảo đảm biểu tượng ứng dụng hiển thị đồng nhất cả trên thanh tiêu đề cửa sổ lẫn Windows Taskbar.

---

## 3. PHÂN HỆ NGHIỆP VỤ & AN TOÀN ĐA LUỒNG

1. **Điều phối luồng UI an toàn (`UiDispatcher` — `modules/ui/dispatch.py`):**
   - Mọi luồng nền (`esptool`, Serial reader, tải bản cập nhật, nháy LED 5s) tuyệt đối không cập nhật widget Qt trực tiếp mà đẩy callback qua hàng đợi an toàn `UiDispatcher.instance().post(...)` về luồng chính Qt (`QTimer` / signal).
2. **Độc quyền tài nguyên cổng Serial (`Exclusive COM Access`):**
   - Khi chạy tác vụ `esptool` tại Tab 1, Tab 3, Tab 4 hoặc Tab 5, hệ thống tạm đóng kết nối Serial Monitor đang mở (nếu trùng cổng), thực thi qua `subprocess` của `esptool`, rồi khôi phục trạng thái giao diện qua `set_global_busy_state(...)`.
3. **Nháy LED nhận diện Board Gốc an toàn (Tab 5):**
   - Mở kết nối PySerial với cờ thụ động `dtr = False, rts = False` và `rtscts = False, dsrdtr = False` nhằm gửi chuỗi xung TX (~10 Hz tối đa 5 giây) mà không kéo chân `EN/GPIO0` gây reset mạch. Tự hủy lập tức khi đổi tab, chọn cổng khác, đóng cửa sổ hoặc khởi chạy tác vụ phần cứng khác.
4. **Kiểm tra an toàn Flash & Engine Phân vùng (`modules/partition/`):**
   - `partition_model.py`: Đóng gói/giải mã cấu trúc 32-byte `PartitionEntry`, kiểm tra Magic `0xAA50` và băm `MD5` theo đúng chuẩn ESP-IDF.
   - `chip_database.py`: Danh mục thông số họ chip ESP32, Bootloader Offset (`0x1000`, `0x0`, `0x2000`) và dải dung lượng Flash hỗ trợ.
   - `unit_formatter.py`: Căn lề 4 KB (`0x1000`) và 64 KB (`0x10000`), kiểm tra trùng lặp địa chỉ trước khi ghi/xóa Flash.

---

## 4. HỆ THỐNG KIỂM THỬ TỰ ĐỘNG (`tests/`)

Bộ kiểm thử sử dụng `pytest` với môi trường offscreen PyQt6 (`tests/mock_hardware/app_harness.py`) và thiết bị giả lập (`mock_serial.py`, `mock_esptool.py`, `mock_registry.py`):
- Kiểm thử lõi & phân vùng: `test_core_utils.py`, `test_partition_wizard.py`, `test_update_util.py`, `test_audit_regressions.py`, `test_release_safety.py`.
- Kiểm thử tích hợp End-to-End giả lập & đối kháng: `test_e2e_mock_tier1..4.py`, `test_challenger_m1_verification.py`, `test_tier5_adversarial_core.py`, `test_tier5_adversarial_hardware.py`.
- **Kiểm thử giao diện & tính năng v1.7 - v1.10:** `test_app_tabs.py`, `test_ui_foundation.py`, `test_ui_widgets.py`, `test_ui_v15.py`, `test_v17_features.py`, `test_v18_features.py`, `test_v19_features.py`, `test_inline_update_ui.py`, `test_v110_features.py`.

---

## 5. ĐƠN THỰC THỂ & GIẢI PHÓNG TÀI NGUYÊN KHI THOÁT (`modules/single_instance.py`)

1. **Khóa đơn thực thể (`SingleInstanceGuard`):**
   - Dùng Win32 `CreateMutexW` (`Local\esp32_manager_tool_single_instance_v1`) trên Windows hoặc khóa file `fcntl.flock` trên POSIX kết hợp máy chủ IPC cục bộ `QLocalServer` / `QLocalSocket`.
   - Khi khởi chạy phiên bản thứ 2, bản mới gửi thông điệp `ACTIVATE` đánh thức cửa sổ đang mở (`bring_to_front`) rồi thoát ngay (`sys.exit(0)`), không tạo luồng nền hay chiếm cổng COM.
2. **Đóng ứng dụng & thu hồi tài nguyên (`MainWindow.cleanup_resources` + `terminate_child_processes`):**
   - Dừng các luồng nền với cờ đánh thức tức thì (`stop_scan.wait(2.0)`, `_stop_board_led_blink`, `stop_serial_thread`), đóng cưỡng bức cổng COM/Serial/nháy LED/`esptool` đang mở (`abort_active_esptool`), dừng bộ đếm `QTimer` của `LogView`, ngừng nhận callback trên `UiDispatcher`, giải phóng GDI icon (`DestroyIcon`) và dừng mọi tiến trình con trực tiếp của tiến trình chính qua Win32 Toolhelp32 snapshot.
