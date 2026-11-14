import sys
import tempfile
import unittest
from pathlib import Path

from video_transcoder.settings.settings_manager import SettingsManager


class SettingsPathTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "POSIX path expectations")
    def test_windows_paths_are_foreign_on_posix(self):
        self.assertTrue(SettingsManager._is_foreign_path(r"E:\Projects\video-transcoder\data"))
        self.assertFalse(SettingsManager._is_foreign_path("/tmp/video-transcoder/data"))

    @unittest.skipUnless(sys.platform == "win32", "Windows path expectations")
    def test_posix_paths_are_foreign_on_windows(self):
        self.assertTrue(SettingsManager._is_foreign_path("/mnt/e/Projects/video-transcoder/data"))
        self.assertFalse(SettingsManager._is_foreign_path(r"E:\Projects\video-transcoder\data"))

    def test_portable_output_dir_is_next_to_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "mt-vtr.exe"
            exe.write_bytes(b"")
            output = SettingsManager._writable_portable_output_dir(exe)
            self.assertEqual(output, Path(tmp) / "transcoded")
            self.assertTrue(output.is_dir())


if __name__ == "__main__":
    unittest.main()
