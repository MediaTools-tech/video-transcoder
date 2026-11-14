import tempfile
import unittest
from pathlib import Path

from video_transcoder.ffmpeg.tool import FFmpegTool


class DummySettings:
    def get(self, key, default=None):
        return {"bin_dir": "bin"}.get(key, default)


class FFmpegToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = FFmpegTool(DummySettings())

    def test_unknown_remote_version_skips_update_prompt(self):
        self.tool.current_platform = "Linux"

        self.assertIsNone(self.tool.get_remote_version())
        self.assertTrue(self.tool.is_up_to_date("7.1", None))

    def test_versioned_remote_url_is_detected(self):
        self.tool.current_platform = "Windows"

        self.assertEqual(self.tool.get_remote_version(), "8.0")

    def test_version_comparison(self):
        self.assertFalse(self.tool.is_up_to_date("7.0", "8.0"))
        self.assertTrue(self.tool.is_up_to_date("8.0", "8.0"))
        self.assertTrue(self.tool.is_up_to_date("8.0.1", "8.0"))

    def test_safe_replace_removes_backup_after_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "ffmpeg.new"
            dst = Path(temp_dir) / "ffmpeg"
            src.write_text("new", encoding="utf-8")
            dst.write_text("old", encoding="utf-8")

            self.assertTrue(self.tool._safe_replace(src, dst))
            self.assertEqual(dst.read_text(encoding="utf-8"), "new")
            self.assertFalse(Path(str(dst) + ".old").exists())


if __name__ == "__main__":
    unittest.main()
