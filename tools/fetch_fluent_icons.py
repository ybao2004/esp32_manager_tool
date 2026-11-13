# -*- coding: utf-8 -*-
"""
Công cụ chuẩn bị icon Fluent UI System Icons (Microsoft, MIT License).
Tự động tải SVG từ GitHub repo chính thức hoặc sinh SVG dự phòng nếu offline.
"""
import os
import urllib.request
import urllib.error

ICONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons", "fluent"))

ICON_MAP = {
    "inspector.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Developer%20Board/SVG/ic_fluent_developer_board_24_regular.svg",
    "monitor.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Window%20Console/SVG/ic_fluent_window_console_24_regular.svg",
    "flash.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Flash/SVG/ic_fluent_flash_24_regular.svg",
    "partition.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Storage/SVG/ic_fluent_storage_24_regular.svg",
    "backup.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Copy%20Arrow%20Right/SVG/ic_fluent_copy_arrow_right_24_regular.svg",
    "settings.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Settings/SVG/ic_fluent_settings_24_regular.svg",
    "menu.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Navigation/SVG/ic_fluent_navigation_24_regular.svg",
    "refresh.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Arrow%20Clockwise/SVG/ic_fluent_arrow_clockwise_24_regular.svg",
    "plug_connected.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Plug%20Connected/SVG/ic_fluent_plug_connected_24_regular.svg",
    "plug_disconnected.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Plug%20Disconnected/SVG/ic_fluent_plug_disconnected_24_regular.svg",
    "play.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Play/SVG/ic_fluent_play_24_regular.svg",
    "stop.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Stop/SVG/ic_fluent_stop_24_regular.svg",
    "add.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Add/SVG/ic_fluent_add_24_regular.svg",
    "delete.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Delete/SVG/ic_fluent_delete_24_regular.svg",
    "edit.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Edit/SVG/ic_fluent_edit_24_regular.svg",
    "open.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Folder%20Open/SVG/ic_fluent_folder_open_24_regular.svg",
    "save.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Save/SVG/ic_fluent_save_24_regular.svg",
    "copy.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Copy/SVG/ic_fluent_copy_24_regular.svg",
    "clear.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Eraser/SVG/ic_fluent_eraser_24_regular.svg",
    "info.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Info/SVG/ic_fluent_info_24_regular.svg",
    "success.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Checkmark%20Circle/SVG/ic_fluent_checkmark_circle_24_regular.svg",
    "warning.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Warning/SVG/ic_fluent_warning_24_regular.svg",
    "error.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Error%20Circle/SVG/ic_fluent_error_circle_24_regular.svg",
    "send.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Send/SVG/ic_fluent_send_24_regular.svg",
    "search.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Search/SVG/ic_fluent_search_24_regular.svg",
    "wifi.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Wifi%201/SVG/ic_fluent_wifi_1_24_regular.svg",
    "server.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Server/SVG/ic_fluent_server_24_regular.svg",
    "align.svg": "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/Align%20Left/SVG/ic_fluent_align_left_24_regular.svg",
}

# SVG Fallback tối giản (dạng nét vector hình học chuẩn viewBox 0 0 24 24) phòng trường hợp offline
FALLBACK_SVG = """<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/>
<path d="M12 7v5l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>"""

LICENSE_TEXT = """MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    with open(os.path.join(ICONS_DIR, "LICENSE"), "w", encoding="utf-8") as f:
        f.write(LICENSE_TEXT)

    for target_name, url in ICON_MAP.items():
        target_path = os.path.join(ICONS_DIR, target_name)
        if os.path.exists(target_path) and os.path.getsize(target_path) > 100:
            continue
        print(f"Downloading {target_name}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode('utf-8')
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
        except Exception as e:
            print(f"[CẢNH BÁO] Không tải được {target_name}: {e}. Ghi SVG dự phòng.")
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(FALLBACK_SVG)

    print("Icons preparation complete.")

if __name__ == '__main__':
    main()
