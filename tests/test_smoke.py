import importlib.util
import unittest


HAS_TKINTER = importlib.util.find_spec("tkinter") is not None


class ImportSmokeTest(unittest.TestCase):
    def test_package_version(self):
        import video_transcoder

        self.assertEqual(video_transcoder.__version__, "1.0.0")

    def test_core_modules_import(self):
        from video_transcoder.app import cli
        from video_transcoder.core import transcoder_engine, transcoder_service
        from video_transcoder.ffmpeg import tool
        from video_transcoder.settings import settings_manager

        self.assertTrue(callable(cli.run_cli))
        self.assertTrue(hasattr(transcoder_engine, "TranscoderEngine"))
        self.assertTrue(hasattr(transcoder_service, "TranscoderService"))
        self.assertTrue(hasattr(tool, "FFmpegTool"))
        self.assertTrue(hasattr(settings_manager, "SettingsManager"))

    @unittest.skipUnless(HAS_TKINTER, "tkinter is not available")
    def test_gui_modules_import(self):
        from video_transcoder.app import launch
        from video_transcoder.gui import main_window
        from video_transcoder.system import shortcut_creator

        self.assertTrue(callable(launch.main))
        self.assertTrue(hasattr(main_window, "VideoTranscoderApp"))
        self.assertTrue(hasattr(shortcut_creator, "ShortcutCreator"))


if __name__ == "__main__":
    unittest.main()
