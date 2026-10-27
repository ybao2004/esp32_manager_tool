# Mức sẵn sàng phát hành — ESP Tool

## Đợt rà soát 3

**Chưa đủ bằng chứng để phát hành thương mại.** Đã tăng kiểm thử và sửa các lỗi dưới đây; chưa có kết quả chạy bo mạch thật, Arduino-CLI thật, EXE hoặc UI thực tế trên các mức DPI.

| Vấn đề phát hiện | Xử lý |
| --- | --- |
| Luồng đọc Serial cũ dùng chung kết nối và sự kiện dừng với phiên mới | Mỗi phiên giữ kết nối, decoder, buffer và sự kiện riêng. Callback cũ bị bỏ khi phiên đã đổi hoặc ngắt. |
| Firmware gộp bị đoán là ứng dụng tại 0x10000; filesystem bị gán cứng 0x290000 | File gộp, filesystem và file không rõ loại không còn được tự tích chọn. Filesystem/file chưa rõ để trống offset, yêu cầu xác nhận. File gộp 0x0 chỉ là gợi ý, không tự chọn. |
| Quét giới hạn độ sâu nhưng vẫn đi tiếp xuống các thư mục con | Cắt danh sách thư mục tại giới hạn để tránh duyệt vô ích. |
| Dừng compiler chỉ kết thúc tiến trình cha và báo xong quá sớm | Windows dùng taskkill theo PID với /T /F, ngoài luồng UI; xử lý yêu cầu hủy trong lúc Popen khởi tạo. Giữ trạng thái bận đến khi tiến trình kết thúc. Cho thử lại khi dừng thất bại. |
| Ghi đè firmware đóng gói mà không hỏi; tên file tạm cố định | Hỏi trước khi ghi đè, dùng file tạm riêng mỗi lần chạy và thay file sau khi lệnh thành công. |
| Có thể đóng app lúc merge hoặc bấm lặp | Thêm trạng thái merge; chặn đóng khi merge đang chạy và bỏ lần bấm trùng. |
| Callback merge thay nội dung tab nạp khi thiết bị đang bận | Giữ file kết quả, báo để chuyển sau khi thiết bị rảnh. |
| Hộp thoại sửa/resize/xóa vùng Flash cố định kích thước | Tính kích thước theo nội dung và cho kéo giãn. Cần kiểm chứng trực quan trên DPI thực tế. |
| Kiểm tra CLI lỗi nếu stdout chỉ có khoảng trắng; cửa sổ console có thể lóe | Xử lý stdout rỗng sau chuẩn hóa và dùng CREATE_NO_WINDOW trên Windows. |

## Bằng chứng kiểm thử

- 63 kiểm thử logic đạt; gồm 14 kiểm thử mới trong `tests/test_release_safety.py`.
- Kiểm tra cú pháp modules/tests đạt.
- `tests/test_ui_layout.py` có kiểm tra footer ở cửa sổ 540×520, mức scaling 1.33/2.0, và giữ dữ liệu chọn mẫu sau vòng lặp sự kiện. Nhóm UI được **skip** do Tcl/Tk không khởi tạo được trong Python môi trường này, không tính là đã đạt.
- Computer Use cũng không khởi tạo được, kể cả sau reset: `failed to write kernel assets: The system cannot find the path specified. (os error 3)`.
- Kiểm thử hủy compiler và lệnh Windows dùng đối tượng giả; chưa chứng minh dọn sạch toàn bộ compiler con trong một build thật.

## Các điều kiện còn thiếu trước phát hành

1. **UI thực tế:** kiểm tra 100/125/150/200% DPI, màn hình nhỏ, light/dark, chuyển màn hình, bàn phím, cuộn và các nút xác nhận/hủy. Kiểm tra cả ứng dụng đóng gói EXE, không chỉ chạy nguồn.
2. **Bo mạch:** ma trận chip/cổng/tốc độ; flash nhiều file, read-back hoặc verify, erase-region, rút cáp giữa tác vụ, kết nối lại, flash được mã hóa/bảo vệ. Không lấy test giả làm bằng chứng tương thích phần cứng.
3. **Build nhất quán:** dùng thư mục kết quả riêng cho mỗi lượt build, metadata về chip/FQBN/core và checksum từng file. Bộ quét hiện vẫn đoán offset cho một số tên file đã biết và nhóm theo thư mục, chưa chứng minh cùng lượt build.
4. **Bản chỉnh sửa phân vùng:** bảo vệ dữ liệu chưa lưu khi đổi dự án/mẫu, tải lại hoặc thoát; thêm khôi phục bản nháp và lịch sử file. Hiện Hoàn tác không thay thế được khôi phục sau thoát/crash.
5. **Phụ thuộc và môi trường:** xác thực board package/core/thư viện, kiểm tra phiên bản tương thích, khóa bộ phụ thuộc đã kiểm chứng và tái lập EXE từ máy sạch.
6. **Chẩn đoán và bảo mật dữ liệu:** log xoay vòng, mã tác vụ và lỗi có ngữ cảnh; loại mật khẩu khỏi log; cơ chế lưu thông tin Wi-Fi phù hợp cho bản phân phối. Cấu hình hiện vẫn lưu mật khẩu dạng đọc được.
7. **Nạp/xóa có căn cứ:** đọc bảng phân vùng thực tế để xác định NVS; đối chiếu chip/dung lượng trước khi ghi; chống dùng artifact cũ hoặc thay đổi giữa lúc kiểm tra và nạp.

Không thực hiện nạp, xóa chip hay thay cài đặt môi trường của người dùng trong đợt này.
