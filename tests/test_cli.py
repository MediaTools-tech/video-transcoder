import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from video_transcoder.app.cli import _resolve_options, build_parser, run_cli


class CliTest(unittest.TestCase):
    def test_help_exits_zero(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                run_cli(["-help"])

        self.assertEqual(caught.exception.code, 0)
        self.assertIn("Transcode with factory-default settings", stdout.getvalue())

    def test_version_exits_zero(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                run_cli(["--version"])

        self.assertEqual(caught.exception.code, 0)
        self.assertIn("1.0.0", stdout.getvalue())

    def test_missing_input_returns_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = run_cli(["-i", "definitely-not-a-real-video.mp4"])

        self.assertEqual(result, 1)
        self.assertIn("input file not found", stderr.getvalue())

    def test_rejects_audio_input_extension(self):
        stderr = io.StringIO()
        with tempfile.NamedTemporaryFile(suffix=".mp3") as audio:
            with contextlib.redirect_stderr(stderr):
                result = run_cli(["-i", audio.name])

        self.assertEqual(result, 1)
        self.assertIn("unsupported input extension", stderr.getvalue())

    def test_parser_accepts_inputs_and_overrides(self):
        args = build_parser().parse_args(
            ["-i", "a.mp4", "-i", "b.mp4", "--container", "mkv", "--crf", "20"]
        )

        self.assertEqual(args.inputs, ["a.mp4", "b.mp4"])
        self.assertEqual(args.container, "mkv")
        self.assertEqual(args.crf, 20)

    def test_parser_accepts_positional_input(self):
        args = build_parser().parse_args(["a.mp4"])

        self.assertEqual(args.files, ["a.mp4"])

    def test_parser_accepts_576p_resolution(self):
        args = build_parser().parse_args(["a.mp4", "--resolution", "576p"])

        self.assertEqual(args.resolution, "576p")

    def test_module_invocation(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")
        result = subprocess.run(
            [sys.executable, "-m", "video_transcoder", "--version"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1.0.0", result.stdout)

    def test_cli_path_does_not_load_tkinter(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")
        code = (
            "import io\n"
            "import sys\n"
            "from contextlib import redirect_stdout\n"
            "from video_transcoder.app import launch\n"
            "with redirect_stdout(io.StringIO()):\n"
            "    try:\n"
            "        launch.main(['--version'])\n"
            "    except SystemExit:\n"
            "        pass\n"
            "print('tkinter' in sys.modules)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False")

    def test_cli_uses_factory_defaults_unless_saved_settings_requested(self):
        settings = {
            "last_container": "mkv",
            "last_video_codec": "av1",
            "last_audio_codec": "opus",
            "last_resolution": "480p",
            "crf": 34,
        }

        defaults_args = build_parser().parse_args(["a.mp4"])
        defaults = _resolve_options(settings, defaults_args)
        self.assertEqual(defaults["container"], "default")
        self.assertEqual(defaults["video_codec"], "default")
        self.assertEqual(defaults["audio_codec"], "default")
        self.assertEqual(defaults["resolution"], "default")
        self.assertEqual(defaults["crf"], 23)

        saved_args = build_parser().parse_args(["a.mp4", "--use-saved-settings"])
        saved = _resolve_options(settings, saved_args)
        self.assertEqual(saved["container"], "mkv")
        self.assertEqual(saved["video_codec"], "av1")
        self.assertEqual(saved["audio_codec"], "opus")
        self.assertEqual(saved["resolution"], "480p")
        self.assertEqual(saved["crf"], 34)


if __name__ == "__main__":
    unittest.main()
