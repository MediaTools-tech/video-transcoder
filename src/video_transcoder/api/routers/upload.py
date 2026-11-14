import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from video_transcoder.api.models import JobResponse, TranscodingOptions
from video_transcoder.api.services import storage
from video_transcoder.api.services.job_manager import job_manager
from video_transcoder.api.services.storage import ALLOWED_SUFFIXES

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/x-msvideo",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "application/octet-stream",
}


def _is_video_upload(upload: UploadFile) -> bool:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return False
    content_type = (upload.content_type or "").lower()
    return content_type in _ALLOWED_CONTENT_TYPES or content_type.startswith("video/")


@router.post("/upload", response_model=JobResponse, status_code=202)
async def upload_video(
    file: UploadFile = File(...),
    options: str = Form(...),
) -> JobResponse:
    if not _is_video_upload(file):
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid video upload. Allowed extensions: {allowed}",
        )

    try:
        parsed_options = TranscodingOptions.model_validate_json(options)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid options: {exc}") from exc

    job_id = uuid.uuid4().hex
    try:
        input_path = await storage.save_upload_file(file, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not store upload") from exc

    try:
        job = job_manager.create_job(
            job_id=job_id,
            filename=Path(file.filename or "video").name,
            input_path=str(input_path),
            options=parsed_options.model_dump(mode="json"),
        )
    except Exception as exc:
        storage.remove_file(input_path)
        raise HTTPException(status_code=500, detail="Could not queue job") from exc

    return JobResponse(**job)
