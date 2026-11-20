import os
import tempfile
import unittest
from pathlib import Path

_TEMP_STORAGE = tempfile.TemporaryDirectory()
_STORAGE = Path(_TEMP_STORAGE.name)
os.environ["UPLOAD_DIR"] = str(_STORAGE / "uploads")
os.environ["TEMP_DIR"] = str(_STORAGE / "temp")
os.environ["OUTPUT_DIR"] = str(_STORAGE / "outputs")

try:
    from fastapi.testclient import TestClient

    from video_transcoder.api.main import app

    HAS_API = True
except ImportError:
    HAS_API = False


def tearDownModule():
    _TEMP_STORAGE.cleanup()


@unittest.skipUnless(HAS_API, "API extras are not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"healthy", "degraded"})
        self.assertIsInstance(payload["ffmpeg_available"], bool)
        self.assertIsInstance(payload["ffprobe_available"], bool)

    def test_readiness(self):
        response = self.client.get("/api/readiness")
        self.assertIn(response.status_code, {200, 503})
        payload = response.json()
        self.assertIsInstance(payload["ready"], bool)
        self.assertEqual(response.status_code == 200, payload["ready"])
        self.assertIn("ffmpeg", payload["checks"])

    def test_list_jobs(self):
        response = self.client.get("/api/jobs/?limit=10")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload["jobs"], list)
        self.assertEqual(payload["total"], len(payload["jobs"]))

    def test_missing_job(self):
        response = self.client.get("/api/jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_rejects_non_video_upload(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("notes.txt", b"not a video", "text/plain")},
            data={"options": "{}"},
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_audio_upload(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("audio.mp3", b"not audio", "audio/mpeg")},
            data={"options": "{}"},
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_options(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("clip.mp4", b"not really an mp4", "video/mp4")},
            data={"options": "not-json"},
        )
        self.assertEqual(response.status_code, 400)

    def test_cancel_missing_job(self):
        response = self.client.post("/api/jobs/does-not-exist/cancel")
        self.assertEqual(response.status_code, 400)

    def test_frontend_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Video Transcoder", response.text)
