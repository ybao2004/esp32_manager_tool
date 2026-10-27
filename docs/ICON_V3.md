# Icon ESP Tool v3

Thiết kế: chip + chữ ESP + cờ-lê, màu than/trắng/xám xanh, nền ngoài trong suốt. Tạo bằng công cụ image_gen tích hợp; xuất PNG/ICO đa kích thước bằng Pillow, giữ alpha. Không thay đổi các file icon v1/v2.

- Nguồn: `icons/esp_icon_v3_master.png` (1254 × 1254).
- Windows: `icons/esp_icon_v3.ico`, gồm 16, 20, 24, 32, 40, 48, 64, 128, 256 px.
- PNG: `icons/esp_icon_v3.png` (256 px) và các file hậu tố kích thước.
- Đã kiểm tra alpha, các frame ICO và xem bản 48 px. Chưa kiểm tra hiển thị trực tiếp trên thanh tiêu đề/taskbar Windows.
- Mã chạy ưu tiên v3; bản EXE cần đóng gói lại để đổi icon nhúng.

Prompt cuối dùng để tinh chỉnh ảnh:

Refine this exact ESP chip-and-wrench icon into production-ready completely flat artwork. Preserve composition, legible large ESP text, chip silhouette and wrench. IMPORTANT fix the dark irregular hole/smudge in the middle-left of the chip, above wrench handle: the entire chip body must be a perfectly uniform solid opaque charcoal #202832 with zero holes, zero spots, zero texture, zero gradients. All white glyphs and wrench perfectly solid #FFFFFF. Pins and wrench inset solid desaturated bluegray #78909C. No bevel, grain, metallic shading, glow or shadows anywhere. Transparency ONLY outside outer chip/pin silhouette and proper wrench cutouts should show same charcoal chip body (not transparency). Maintain clean bold sharp geometry and uniform flat fills. Single icon, transparent outer background, square 1024 or larger. No additional text. This is final Windows icon asset.
