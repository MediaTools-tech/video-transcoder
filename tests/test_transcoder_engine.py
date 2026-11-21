import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from video_transcoder.core.transcoder_engine import (
    SHARPENING_FILTERS,
    SHARPENING_LABELS,
    TranscoderEngine,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "test_1.mp4"


class ResolutionTest(unittest.TestCase):
    def setUp(self):
        self.engine = TranscoderEngine("ffmpeg", "ffprobe")

    def test_nearest_standard_resolution_includes_576p(self):
        self.assertEqual(self.engine.get_nearest_standard_resolution(1024, 576), "576p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(720, 540), "576p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(1280, 577), "720p")

    def test_nearest_standard_resolution_uses_short_side(self):
        self.assertEqual(self.engine.get_nearest_standard_resolution(1080, 1920), "1080p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(1920, 1080), "1080p")
        self.assertEqual(self.engine.get_nearest_standard_resolution(720, 1280), "720p")

    def test_576p_scale_filter(self):
        self.assertEqual(
            self.engine.get_smart_scale_filter(1920, 1080, "576p"),
            "scale=1024:576:flags=lanczos",
        )
        self.assertEqual(
            self.engine.get_smart_scale_filter(2560, 1080, "576p"),
            "scale=1024:432:flags=lanczos",
        )

    def test_portrait_uses_rotated_bounding_box(self):
        self.assertEqual(
            self.engine.get_smart_scale_filter(1080, 1920, "720p"),
            "scale=720:1280:flags=lanczos",
        )
        self.assertIsNone(
            self.engine.get_smart_scale_filter(720, 1280, "720p")
        )

    def test_smaller_sources_are_upscaled_inside_the_box(self):
        self.assertEqual(
            self.engine.get_smart_scale_filter(640, 480, "720p"),
            "scale=960:720:flags=lanczos",
        )
        self.assertEqual(
            self.engine.get_smart_scale_filter(640, 360, "720p"),
            "scale=1280:720:flags=lanczos",
        )
        self.assertEqual(
            self.engine.get_smart_scale_filter(300, 300, "720p"),
            "scale=720:720:flags=lanczos",
        )

    def test_output_never_exceeds_the_target_box(self):
        samples = [
            (64, 36),
            (100, 100),
            (640, 360),
            (640, 400),
            (640, 480),
            (720, 1280),
            (1001, 563),
            (1080, 1920),
            (1440, 1080),
            (1919, 1079),
            (2160, 3840),
            (2560, 1080),
            (3840, 2160),
        ]
        for target, bounds in self.engine.RESOLUTION_BOUNDS.items():
            target_long, target_short = max(bounds), min(bounds)
            for width, height in samples:
                result = self.engine.get_smart_scale_filter(width, height, target)
                if result is None:
                    continue
                out_width, out_height = map(
                    int, result.split("=")[1].split(":flags")[0].split(":")
                )
                if height > width:
                    max_width, max_height = target_short, target_long
                else:
                    max_width, max_height = target_long, target_short
                self.assertLessEqual(out_width, max_width, result)
                self.assertLessEqual(out_height, max_height, result)
                self.assertEqual(out_width % 2, 0, result)
                self.assertEqual(out_height % 2, 0, result)

    def test_invalid_inputs_return_none(self):
        self.assertIsNone(self.engine.get_smart_scale_filter(1920, 1080, "unknown"))
        self.assertIsNone(self.engine.get_smart_scale_filter(0, 0, "1080p"))


class InputPolicyTest(unittest.TestCase):
    def setUp(self):
        self.engine = TranscoderEngine("ffmpeg", "ffprobe")

    def test_audio_only_metadata_has_no_video_stream(self):
        info = {
            "streams": [
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }
        self.assertFalse(self.engine.has_video_stream(info))

    def test_attached_picture_is_not_a_video_stream(self):
        info = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "mjpeg",
                    "disposition": {"attached_pic": 1},
                },
            ]
        }
        self.assertFalse(self.engine.has_video_stream(info))

    def test_transcode_rejects_unsupported_extension_before_probe(self):
        with self.assertRaisesRegex(ValueError, "Unsupported input extension"):
            self.engine.transcode_video("input.txt", "output.mp4", {})

    def test_transcode_rejects_audio_only_input(self):
        info = {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
        with patch.object(self.engine, "get_video_info", return_value=info):
            with self.assertRaisesRegex(ValueError, "Audio-only inputs"):
                self.engine.transcode_video("input.mp4", "output.mp4", {})

    @unittest.skipUnless(
        FIXTURE.is_file() and shutil.which("ffprobe"),
        "basic transcoder fixture or ffprobe is unavailable",
    )
    def test_basic_fixture_contains_a_video_stream(self):
        info = self.engine.get_video_info(str(FIXTURE))
        self.assertIsNotNone(info)
        self.assertTrue(self.engine.has_video_stream(info))


class SharpeningTest(unittest.TestCase):
    def test_labels_cover_every_filter(self):
        self.assertEqual(set(SHARPENING_LABELS), set(SHARPENING_FILTERS))

    def test_labels_match_display_options(self):
        self.assertEqual(SHARPENING_LABELS["light"], "Light")
        self.assertEqual(SHARPENING_LABELS["medium"], "Medium")
        self.assertEqual(SHARPENING_LABELS["strong"], "Strong")
        self.assertIn("CAS", SHARPENING_LABELS["adaptive"])


class ProcessPauseTest(unittest.TestCase):
    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

    def setUp(self):
        self.engine = TranscoderEngine("ffmpeg", "ffprobe")
        self.engine.active_process = self.FakeProcess()

    def test_suspend_and_resume_active_process(self):
        with patch(
            "video_transcoder.core.transcoder_engine._set_process_suspended"
        ) as set_suspended:
            self.assertTrue(self.engine.suspend_active_process())
            self.assertTrue(self.engine._process_suspended)
            set_suspended.assert_called_once_with(4321, True)

            self.assertTrue(self.engine.suspend_active_process())
            set_suspended.assert_called_once_with(4321, True)

            self.assertTrue(self.engine.resume_active_process())
            self.assertFalse(self.engine._process_suspended)
            set_suspended.assert_called_with(4321, False)

    def test_suspend_without_active_process_returns_false(self):
        self.engine.active_process = None
        self.assertFalse(self.engine.suspend_active_process())


if __name__ == "__main__":
    unittest.main()
