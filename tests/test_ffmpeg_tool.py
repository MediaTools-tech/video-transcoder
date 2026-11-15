import tempfile
import unittest
from pathlib import Path
from unittest import mock

from video_transcoder.ffmpeg.tool import FFmpegTool


class DummySettings:
    def get(self, key, default=None):
        return {"bin_dir": "bin"}.get(key, default)


class TempSettings:
    def __init__(self, bin_dir):
        self.bin_dir = str(bin_dir)

    def get(self, key, default=None):
        return self.bin_dir if key == "bin_dir" else default


class FakeResponse:
    headers = {"content-length": "7"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield b"archive"


class FakeZipFile:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


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

    def test_version_comparison_orders_versions(self):
        self.assertTrue(self.tool.is_up_to_date("8.1", "8.0"))
        self.assertTrue(self.tool.is_up_to_date("18.0", "8.0"))
        self.assertFalse(self.tool.is_up_to_date("7.9", "8.0"))
        self.assertFalse(self.tool.is_up_to_date("unknown", "8.0"))

    def test_is_ffmpeg_available_handles_oserror(self):
        with mock.patch.object(self.tool, "is_ffmpeg_downloaded", return_value=False):
            with mock.patch(
                "video_transcoder.ffmpeg.tool.subprocess.run",
                side_effect=PermissionError("not executable"),
            ):
                self.assertFalse(self.tool.is_ffmpeg_available())

    def test_safe_replace_removes_backup_after_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "ffmpeg.new"
            dst = Path(temp_dir) / "ffmpeg"
            src.write_text("new", encoding="utf-8")
            dst.write_text("old", encoding="utf-8")

            self.assertTrue(self.tool._safe_replace(src, dst))
            self.assertEqual(dst.read_text(encoding="utf-8"), "new")
            self.assertFalse(Path(str(dst) + ".old").exists())

    def test_failed_ffprobe_replacement_restores_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = Path(temp_dir)
            tool = FFmpegTool(TempSettings(bin_dir))
            tool.current_platform = "Windows"
            ffmpeg_final = Path(tool.get_ffmpeg_path())
            ffprobe_final = Path(tool.get_ffprobe_path())
            ffmpeg_final.write_text("old-ffmpeg", encoding="utf-8")
            ffprobe_final.write_text("old-ffprobe", encoding="utf-8")

            def fake_extract(zip_ref, filename, destination):
                Path(destination).write_text(f"new-{filename}", encoding="utf-8")
                return True

            replace_calls = []

            def fake_replace(src, dst):
                replace_calls.append((Path(src), Path(dst)))
                if len(replace_calls) == 2:
                    raise OSError("ffprobe is locked")
                Path(dst).write_text(
                    Path(src).read_text(encoding="utf-8"), encoding="utf-8"
                )
                return True

            with mock.patch(
                "video_transcoder.ffmpeg.tool.requests.get",
                return_value=FakeResponse(),
            ), mock.patch(
                "video_transcoder.ffmpeg.tool.zipfile.ZipFile",
                return_value=FakeZipFile(),
            ), mock.patch.object(
                tool, "_extract_zip_member", side_effect=fake_extract
            ), mock.patch.object(
                tool, "_safe_replace", side_effect=fake_replace
            ):
                with self.assertRaises(OSError):
                    tool.download_and_extract()

            self.assertEqual(len(replace_calls), 3)
            self.assertEqual(ffmpeg_final.read_text(encoding="utf-8"), "old-ffmpeg")
            self.assertEqual(ffprobe_final.read_text(encoding="utf-8"), "old-ffprobe")


if __name__ == "__main__":
    unittest.main()
