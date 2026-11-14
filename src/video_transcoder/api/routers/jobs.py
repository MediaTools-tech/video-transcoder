import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from video_transcoder.api.models import JobListResponse, JobResponse
from video_transcoder.api.services.job_manager import JobBusyError, job_manager

router = APIRouter()

_MEDIA_TYPES = {
    "mp4": "video/mp4",
    "mkv": "video/x-matroska",
    "avi": "video/x-msvideo",
    "webm": "video/webm",
    "mov": "video/quicktime",
}


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> JobListResponse:
    jobs = [JobResponse(**job) for job in job_manager.list_jobs(status=status, limit=limit)]
    return JobListResponse(jobs=jobs, total=len(jobs))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@router.get("/{job_id}/download")
async def download_video(job_id: str) -> FileResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job['status']}",
        )

    output_path = job.get("output_path")
    if not output_path or not os.path.isfile(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    suffix = Path(output_path).suffix.lstrip(".").lower()
    download_name = f"{Path(job['filename']).stem}.{suffix}" if suffix else Path(output_path).name
    return FileResponse(
        path=output_path,
        media_type=_MEDIA_TYPES.get(suffix, "application/octet-stream"),
        filename=download_name,
    )


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    if not job_manager.cancel_job(job_id):
        raise HTTPException(
            status_code=400,
            detail="Could not cancel job. Job not found or already finished.",
        )
    return {"message": "Job cancellation initiated", "job_id": job_id}


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> dict:
    try:
        deleted = job_manager.delete_job(job_id)
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job deleted successfully", "job_id": job_id}
