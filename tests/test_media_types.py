import unittest
from pathlib import Path

from video_transcoder.core.media_types import (
    VIDEO_INPUT_EXTENSIONS,
    VIDEO_INPUT_FILE_TYPES,
    format_supported_video_extensions,
    is_supported_video_extension,
    is_supported_video_path,
)


class MediaTypePolicyTest(unittest.TestCase):
    def test_common_video_extensions_are_supported(self):
        expected = {
            ".3g2",
            ".3gp",
            ".avi",
            ".flv",
            ".gif",
            ".m2ts",
            ".m4v",
            ".mkv",
            ".mov",
            ".mp4",
            ".mpeg",
            ".mpg",
            ".mxf",
            ".ogg",
            ".ogv",
            ".rm",
            ".rmvb",
            ".ts",
            ".vob",
            ".webm",
            ".webp",
            ".wmv",
        }
        self.assertTrue(expected.issubset(VIDEO_INPUT_EXTENSIONS))

    def test_audio_and_arbitrary_extensions_are_not_supported(self):
        for extension in (".mp3", ".m4a", ".wav", ".flac", ".aac", ".txt", ".exe", ".dll"):
            with self.subTest(extension=extension):
                self.assertFalse(is_supported_video_extension(extension))

    def test_extensions_are_case_insensitive(self):
        self.assertTrue(is_supported_video_extension("MP4"))
        self.assertTrue(is_supported_video_extension(".GiF"))
        self.assertTrue(is_supported_video_path(Path("clip.M2TS")))

    def test_file_dialog_filter_includes_extensions(self):
        pattern = VIDEO_INPUT_FILE_TYPES[0][1]
        self.assertIn("*.mp4", pattern)
        self.assertIn("*.gif", pattern)
        self.assertIn("*.mpg", pattern)

    def test_format_is_stable_and_readable(self):
        formatted = format_supported_video_extensions()
        self.assertIn(".mp4", formatted)
        self.assertIn(".webp", formatted)
        self.assertEqual(formatted, format_supported_video_extensions())


if __name__ == "__main__":
    unittest.main()
