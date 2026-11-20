import os
import re
import shutil
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from video_transcoder.api.config import settings
from video_transcoder.core.media_types import VIDEO_INPUT_EXTENSIONS


def ensure_storage_dirs() -> None:
    for directory in (settings.upload_dir, settings.temp_dir, settings.output_dir):
        directory.mkdir(parents=True, exist_ok=True)


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip() or "video"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .")
    return (stem or "video")[:120]


def _is_managed_path(path: Path) -> bool:
    roots = (
        settings.upload_dir.resolve(),
        settings.temp_dir.resolve(),
        settings.output_dir.resolve(),
    )
    resolved = path.resolve()
    return any(resolved == root or resolved.is_relative_to(root) for root in roots)


def temp_path(job_id: str, extension: str) -> Path:
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    return settings.temp_dir / f"{job_id}.{extension.lstrip('.')}"


def unique_output_path(original_filename: str, extension: str) -> Path:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(original_filename)
    ext = extension.lower().lstrip(".")
    candidate = settings.output_dir / f"{stem}.{ext}"
    if not candidate.exists():
        return candidate

    counter = 1
    while True:
        candidate = settings.output_dir / f"{stem}_{counter}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


async def save_upload_file(upload: UploadFile, job_id: str) -> Path:
    """Stream an upload to disk without loading the whole file into memory."""
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_INPUT_EXTENSIONS:
        allowed = ", ".join(sorted(VIDEO_INPUT_EXTENSIONS))
        raise ValueError(f"Unsupported video extension. Allowed: {allowed}")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / f"{job_id}{suffix}"
    size = 0

    try:
        async with aiofiles.open(target, "wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                await handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    if size == 0:
        target.unlink(missing_ok=True)
        raise ValueError("Uploaded file is empty")

    return target


def move_temp_to_output(temp_file: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temp_file), str(target))
    return target


def remove_file(path: Path | str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def delete_job_files(input_path: str, output_path: str | None = None) -> None:
    for value in (input_path, output_path):
        if not value:
            continue
        path = Path(value)
        if not _is_managed_path(path):
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def get_file_size_mb(file_path: str | os.PathLike[str]) -> float:
    path = Path(file_path)
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 2)
