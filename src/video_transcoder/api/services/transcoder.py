import threading
from pathlib import Path
from typing import Callable

from video_transcoder.api.config import settings
from video_transcoder.core.transcoder_engine import TranscoderEngine


class TranscodeRunner:
    """One engine instance per job so cancellation cannot affect another job."""

    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.engine = TranscoderEngine(settings.ffmpeg_path, settings.ffprobe_path)

    def run(
        self,
        input_path: Path,
        output_path: Path,
        options: dict,
        progress_callback: Callable[[int, str], None],
    ) -> None:
        self.engine.transcode_video(
            str(input_path),
            str(output_path),
            options,
            progress_callback=progress_callback,
            stop_event=self.stop_event,
        )

    def cancel(self) -> None:
        self.stop_event.set()
        self.engine.terminate_active_process()
