import io
import os
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from modules.update_util import (
    parse_version_tuple,
    is_newer_version,
    check_for_updates,
    download_update_asset,
    is_same_target_as_running_exe,
    get_staged_update_path,
    build_windows_self_update_script,
    launch_windows_self_updater,
)


class UpdateUtilTests(unittest.TestCase):
    def test_parse_version_tuple(self):
        self.assertEqual(parse_version_tuple("1.0"), (1, 0))
        self.assertEqual(parse_version_tuple("v1.0"), (1, 0))
        self.assertEqual(parse_version_tuple("v2.1.3"), (2, 1, 3))
        self.assertEqual(parse_version_tuple(""), (0,))
        self.assertEqual(parse_version_tuple("beta"), (0,))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("v1.1", "1.0"))
        self.assertTrue(is_newer_version("v1.0.1", "1.0"))
        self.assertTrue(is_newer_version("2.0", "1.9"))
        self.assertFalse(is_newer_version("v1.0", "1.0"))
        self.assertFalse(is_newer_version("v0.9", "1.0"))
        self.assertFalse(is_newer_version("1.0", "1.1"))

    @patch("urllib.request.urlopen")
    def test_check_for_updates_found_newer(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            b'{"tag_name": "v1.2", "name": "Esp32 Manager Tool v1.2", "body": "- Feature X", '
            b'"published_at": "2026-10-30T10:00:00Z", '
            b'"assets": [{"name": "Esp32_manager_tool.exe", "browser_download_url": "https://github.com/test/download.exe", "size": 35000000}]}'
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = check_for_updates(current_version="1.0", repo="ybao2004/esp32_manager_tool")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["has_update"])
        self.assertEqual(res["latest_version"], "v1.2")
        self.assertEqual(res["asset_name"], "Esp32_manager_tool.exe")
        self.assertEqual(res["download_url"], "https://github.com/test/download.exe")

    @patch("urllib.request.urlopen")
    def test_check_for_updates_no_releases(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None
        )

        res = check_for_updates(current_version="1.0", repo="ybao2004/esp32_manager_tool")
        self.assertEqual(res["status"], "no_releases")
        self.assertFalse(res["has_update"])
        self.assertIn("Chưa có bản phát hành", res["message"])

    @patch("urllib.request.urlopen")
    def test_download_update_asset(self, mock_urlopen):
        dummy_content = b"fake binary executable content" * 100
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(dummy_content))}
        mock_resp.read.side_effect = [dummy_content[:200], dummy_content[200:], b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "downloaded_app.exe")
            progress_calls = []

            def on_progress(pct, cur, total):
                progress_calls.append((pct, cur, total))

            success, path = download_update_asset(
                download_url="https://example.com/app.exe",
                dest_path=dest,
                progress_callback=on_progress
            )
            self.assertTrue(success)
            self.assertTrue(os.path.isfile(dest))
            self.assertEqual(os.path.getsize(dest), len(dummy_content))
            self.assertTrue(len(progress_calls) > 0)

    @patch("urllib.request.urlopen")
    def test_download_update_asset_overwrites_existing_file_without_winerror183(self, mock_urlopen):
        new_content = b"new updated binary payload"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(new_content))}
        mock_resp.read.side_effect = [new_content, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "Esp32_manager_tool.exe")
            with open(dest, "wb") as fp:
                fp.write(b"old binary payload")

            success, path = download_update_asset(
                download_url="https://example.com/app.exe",
                dest_path=dest,
            )
            self.assertTrue(success)
            self.assertEqual(path, dest)
            with open(dest, "rb") as fp:
                self.assertEqual(fp.read(), new_content)

    def test_is_same_target_as_running_exe_and_blocks_direct_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_exe = os.path.join(tmp_dir, "Esp32_manager_tool.exe")
            with open(fake_exe, "wb") as fp:
                fp.write(b"running")

            with patch("modules.update_util.sys.frozen", True, create=True), \
                 patch("modules.update_util.sys.executable", fake_exe):
                self.assertTrue(is_same_target_as_running_exe(fake_exe))
                self.assertTrue(is_same_target_as_running_exe(fake_exe.replace("\\", "/").lower()))
                self.assertFalse(is_same_target_as_running_exe(os.path.join(tmp_dir, "other.exe")))

                ok, msg = download_update_asset("https://example.com/app.exe", fake_exe)
                self.assertFalse(ok)
                self.assertIn("đang chạy", msg)

    def test_staged_path_and_self_update_script_builder(self):
        staged = get_staged_update_path("Esp32_manager_tool.exe")
        self.assertTrue(staged.endswith("Esp32_manager_tool.exe"))
        self.assertIn(str(os.getpid()), os.path.basename(staged))

        script = build_windows_self_update_script(
            staged_exe_path=r"C:\Temp\new.exe",
            target_exe_path=r"D:\Apps\Esp32_manager_tool.exe",
            current_pid=4242,
            relaunch=True,
        )
        self.assertIn("4242", script)
        self.assertIn('move /Y "%SRC_EXE%" "%DST_EXE%"', script)
        self.assertIn('start ""', script)

    def test_launch_windows_self_updater_runs_hidden_without_detached_process(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            staged = os.path.join(tmp_dir, "staged.exe")
            target = os.path.join(tmp_dir, "Esp32_manager_tool.exe")
            with open(staged, "wb") as fp:
                fp.write(b"new")

            fake_proc = MagicMock(pid=9999)
            with patch("modules.update_util.os.name", "nt"), \
                 patch("modules.update_util.subprocess.Popen", return_value=fake_proc) as mock_popen:
                ok, script_path = launch_windows_self_updater(staged, target, current_pid=1234, relaunch=True)
                self.assertTrue(ok)
                self.assertTrue(os.path.isfile(script_path))
                mock_popen.assert_called_once()
                _, kwargs = mock_popen.call_args
                flags = kwargs["creationflags"]
                import subprocess as _sp
                self.assertEqual(flags & getattr(_sp, "DETACHED_PROCESS", 0), 0)
                if hasattr(_sp, "CREATE_NO_WINDOW"):
                    self.assertNotEqual(flags & _sp.CREATE_NO_WINDOW, 0)
                si = kwargs.get("startupinfo")
                if hasattr(_sp, "STARTUPINFO"):
                    self.assertIsNotNone(si)
                    self.assertNotEqual(si.dwFlags & _sp.STARTF_USESHOWWINDOW, 0)
                    self.assertEqual(si.wShowWindow, 0)
                try:
                    os.remove(script_path)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
