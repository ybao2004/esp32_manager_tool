import io
import os
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from modules.update_util import (
    parse_version_tuple, is_newer_version, check_for_updates, download_update_asset
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


if __name__ == "__main__":
    unittest.main()
