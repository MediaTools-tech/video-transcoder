import unittest

from video_transcoder.core.transcoder_service import TranscoderService


class DummyEngine:
    def __init__(self):
        self.terminated = False

    def terminate_active_process(self):
        self.terminated = True


class TranscoderServiceTest(unittest.TestCase):
    def test_cleanup_stops_worker_and_terminates_active_process(self):
        engine = DummyEngine()
        service = TranscoderService(engine, None)

        service.cleanup()

        self.assertTrue(service.stop_event.is_set())
        self.assertTrue(service.pause_event.is_set())
        self.assertTrue(engine.terminated)


if __name__ == "__main__":
    unittest.main()
