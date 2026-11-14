import unittest

from video_transcoder.core.transcoder_engine import (
    SHARPENING_FILTERS,
    SHARPENING_LABELS,
    TranscoderEngine,
)


class ResolutionTest(unittest.TestCase):
    def setUp(self):
        self.engine = TranscoderEngine("ffmpeg", "ffprobe")

    def test_nearest_standard_resolution_includes_576p(self):
        self.assertEqual(self.engine.get_nearest_standard_resolution(1024, 576), "576p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(720, 540), "576p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(1280, 577), "720p")

    def test_576p_scale_filter(self):
        self.assertEqual(
            self.engine.get_smart_scale_filter(1920, 1080, "576p"),
            "scale=-2:576:flags=lanczos",
        )
        self.assertEqual(
            self.engine.get_smart_scale_filter(2560, 1080, "576p"),
            "scale=1024:-2:flags=lanczos",
        )


class SharpeningTest(unittest.TestCase):
    def test_labels_cover_every_filter(self):
        self.assertEqual(set(SHARPENING_LABELS), set(SHARPENING_FILTERS))

    def test_labels_describe_filter_types(self):
        self.assertIn("Unsharp", SHARPENING_LABELS["light"])
        self.assertIn("Unsharp", SHARPENING_LABELS["strong"])
        self.assertIn("CAS", SHARPENING_LABELS["adaptive"])


if __name__ == "__main__":
    unittest.main()
