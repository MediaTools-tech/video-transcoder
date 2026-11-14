import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from video_transcoder.api.config import settings
from video_transcoder.api.services import storage
from video_transcoder.api.services.transcoder import TranscodeRunner
from video_transcoder.core.transcoder_engine import CONTAINERS

logger = logging.getLogger(__name__)


class JobBusyError(RuntimeError):
    """Raised when a queued or running job would be deleted."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobManager:
    """In-memory, single-process job queue.

    The Docker image runs exactly one Uvicorn worker because job state and
    cancellation handles live in this process. Persist state externally before
    scaling to multiple workers/replicas.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._runners: dict[str, TranscodeRunner] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._output_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_jobs)

    def create_job(
        self,
        job_id: str,
        filename: str,
        input_path: str,
        options: dict,
    ) -> dict:
        now = _utcnow()
        job = {
            "job_id": job_id,
            "filename": filename,
            "status": "queued",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "error_message": None,
            "input_path": input_path,
            "output_path": None,
            "file_size_mb": None,
            "options": options,
        }
        stop_event = threading.Event()

        with self._lock:
            self._jobs[job_id] = job
            self._stop_events[job_id] = stop_event

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, stop_event),
            name=f"transcode-{job_id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return dict(job)

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        with self._lock:
            jobs = [dict(job) for job in self._jobs.values()]
        if status:
            jobs = [job for job in jobs if job["status"] == status]
        jobs.sort(key=lambda job: job["created_at"], reverse=True)
        return jobs[:limit]

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] in {"completed", "failed", "cancelled"}:
                return False

            stop_event = self._stop_events.get(job_id)
            if stop_event:
                stop_event.set()

            runner = self._runners.get(job_id)
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["updated_at"] = _utcnow()
                job["completed_at"] = _utcnow()

        if runner:
            runner.cancel()
        return True

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job["status"] in {"queued", "processing"}:
                raise JobBusyError("Cancel the job before deleting it")

            input_path = job["input_path"]
            output_path = job.get("output_path")
            del self._jobs[job_id]
            self._stop_events.pop(job_id, None)
            self._threads.pop(job_id, None)

        storage.delete_job_files(input_path, output_path)
        return True

    def shutdown(self) -> None:
        with self._lock:
            events = list(self._stop_events.values())
            runners = list(self._runners.values())
            threads = list(self._threads.values())

        for event in events:
            event.set()
        for runner in runners:
            runner.cancel()
        for thread in threads:
            thread.join(timeout=5)

    def _run_job(self, job_id: str, stop_event: threading.Event) -> None:
        acquired = False
        while not acquired and not stop_event.is_set():
            acquired = self._slots.acquire(timeout=0.5)

        if not acquired:
            self._mark_cancelled(job_id)
            self._forget_thread(job_id)
            return

        runner: Optional[TranscodeRunner] = None
        temp_file = None
        try:
            with self._lock:
                job = self._jobs.get(job_id)
                if not job or stop_event.is_set() or job["status"] == "cancelled":
                    self._mark_cancelled_locked(job_id)
                    return
                job["status"] = "processing"
                job["updated_at"] = _utcnow()
                job["error_message"] = None
                filename = job["filename"]
                input_path = job["input_path"]
                options = dict(job["options"])

            extension = CONTAINERS.get(options.get("container", "default"), "mp4")
            temp_file = storage.temp_path(job_id, extension)
            runner = TranscodeRunner(stop_event)
            with self._lock:
                self._runners[job_id] = runner

            runner.run(
                input_path=Path(input_path),
                output_path=temp_file,
                options=options,
                progress_callback=lambda progress, _line: self._update_progress(
                    job_id, progress
                ),
            )

            if stop_event.is_set():
                storage.remove_file(temp_file)
                self._mark_cancelled(job_id)
                return

            with self._output_lock:
                output_path = storage.unique_output_path(filename, extension)
                storage.move_temp_to_output(temp_file, output_path)
            temp_file = None
            self._mark_completed(job_id, output_path)
        except Exception as exc:
            storage.remove_file(temp_file)
            if stop_event.is_set():
                self._mark_cancelled(job_id)
            else:
                logger.exception("Transcode job %s failed", job_id)
                self._mark_failed(job_id, str(exc))
        finally:
            if runner:
                with self._lock:
                    self._runners.pop(job_id, None)
            self._slots.release()
            self._forget_thread(job_id)

    def _update_progress(self, job_id: str, progress: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] != "processing":
                return
            progress = max(0, min(int(progress), 99))
            if progress > job["progress"]:
                job["progress"] = progress
                job["updated_at"] = _utcnow()

    def _mark_completed(self, job_id: str, output_path: Path) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            now = _utcnow()
            job.update(
                {
                    "status": "completed",
                    "progress": 100,
                    "output_path": str(output_path),
                    "file_size_mb": storage.get_file_size_mb(output_path),
                    "completed_at": now,
                    "updated_at": now,
                }
            )

    def _mark_failed(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            now = _utcnow()
            job.update(
                {
                    "status": "failed",
                    "error_message": message,
                    "completed_at": now,
                    "updated_at": now,
                }
            )

    def _mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            self._mark_cancelled_locked(job_id)

    def _mark_cancelled_locked(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or job["status"] in {"completed", "failed"}:
            return
        now = _utcnow()
        job.update(
            {
                "status": "cancelled",
                "completed_at": now,
                "updated_at": now,
            }
        )

    def _forget_thread(self, job_id: str) -> None:
        with self._lock:
            self._threads.pop(job_id, None)


job_manager = JobManager()
