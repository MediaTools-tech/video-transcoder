import tempfile
import threading
import time
import unittest
from pathlib import Path

from video_transcoder.core.transcoder_service import TranscoderService


class DummyEngine:
    def __init__(self):
        self.terminated = False
        self.suspended = False
        self.resumed = False

    def suspend_active_process(self):
        self.suspended = True
        return True

    def resume_active_process(self):
        self.resumed = True
        return True

    def terminate_active_process(self):
        self.terminated = True


class BlockingEngine(DummyEngine):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def transcode_video(self, *args, **kwargs):
        self.started.set()
        self.release.wait(5)


class CancellingEngine(BlockingEngine):
    def transcode_video(self, input_path, output_path, *args, **kwargs):
        Path(output_path).write_bytes(b"partial output")
        self.started.set()
        self.release.wait(5)


class TranscoderServiceTest(unittest.TestCase):
    def test_cleanup_stops_worker_and_terminates_active_process(self):
        engine = DummyEngine()
        service = TranscoderService(engine, None)

        service.cleanup()

        self.assertTrue(service.stop_event.is_set())
        self.assertFalse(service.pause_event.is_set())
        self.assertTrue(engine.resumed)
        self.assertTrue(engine.terminated)

    def test_pause_suspends_active_process_without_stopping_batch(self):
        engine = DummyEngine()
        service = TranscoderService(engine, None)
        service.is_active = True

        service.pause()

        self.assertTrue(service.pause_event.is_set())
        self.assertFalse(service.stop_event.is_set())
        self.assertTrue(engine.suspended)

    def test_resume_clears_pause_and_resumes_active_process(self):
        engine = DummyEngine()
        service = TranscoderService(engine, None)
        service.pause_event.set()

        service.resume()

        self.assertFalse(service.pause_event.is_set())
        self.assertTrue(engine.resumed)

    def test_stop_clears_pause_and_resumes_process_before_worker_exits(self):
        engine = DummyEngine()
        service = TranscoderService(engine, None)
        service.pause_event.set()

        service.stop()

        self.assertTrue(service.stop_event.is_set())
        self.assertFalse(service.pause_event.is_set())
        self.assertTrue(engine.resumed)
        self.assertFalse(engine.terminated)

    def test_pause_does_not_finish_batch_and_resume_continues_worker(self):
        engine = BlockingEngine()
        service = TranscoderService(engine, None)
        finished = threading.Event()
        reasons = []

        def callback(event_type, data):
            if event_type == "finished":
                reasons.append(data)
                finished.set()

        with tempfile.TemporaryDirectory() as output_dir:
            service.start_batch(["input.mp4"], output_dir, {}, callback)
            self.assertTrue(engine.started.wait(2))

            service.pause()
            time.sleep(0.2)
            self.assertFalse(finished.is_set())
            self.assertTrue(service.pause_event.is_set())

            service.resume()
            engine.release.set()
            self.assertTrue(finished.wait(2))

        self.assertEqual(reasons, ["Done"])

    def test_cancel_deletes_partial_output(self):
        engine = CancellingEngine()
        service = TranscoderService(engine, None)
        finished = threading.Event()
        reasons = []

        def callback(event_type, data):
            if event_type == "finished":
                reasons.append(data)
                finished.set()

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "input.mp4"
            service.start_batch(["input.mp4"], output_dir, {}, callback)
            self.assertTrue(engine.started.wait(2))
            self.assertTrue(output_path.exists())

            service.stop()
            engine.release.set()
            self.assertTrue(finished.wait(2))

            self.assertFalse(output_path.exists())

        self.assertEqual(reasons, ["Cancelled"])


if __name__ == "__main__":
    unittest.main()
