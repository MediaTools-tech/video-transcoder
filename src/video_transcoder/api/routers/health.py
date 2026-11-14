import asyncio
import os
import shutil
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from video_transcoder.api.config import settings
from video_transcoder.api.models import HealthResponse, ReadinessResponse

router = APIRouter()


def _binary_status(binary: str) -> tuple[bool, str | None]:
    resolved = shutil.which(binary)
    if not resolved:
        return False, None
    try:
        result = subprocess.run(
            [resolved, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    if result.returncode != 0:
        return False, None
    output = (result.stdout or result.stderr).splitlines()
    return True, output[0].strip() if output else None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    (ffmpeg_available, ffmpeg_version), (ffprobe_available, _) = await asyncio.gather(
        asyncio.to_thread(_binary_status, settings.ffmpeg_path),
        asyncio.to_thread(_binary_status, settings.ffprobe_path),
    )
    healthy = ffmpeg_available and ffprobe_available
    return HealthResponse(
        status="healthy" if healthy else "degraded",
        timestamp=datetime.now(timezone.utc),
        ffmpeg_available=ffmpeg_available,
        ffprobe_available=ffprobe_available,
        ffmpeg_version=ffmpeg_version,
    )


@router.get("/readiness", response_model=ReadinessResponse)
async def readiness_check(response: Response) -> ReadinessResponse:
    (ffmpeg_available, _), (ffprobe_available, _) = await asyncio.gather(
        asyncio.to_thread(_binary_status, settings.ffmpeg_path),
        asyncio.to_thread(_binary_status, settings.ffprobe_path),
    )
    checks = {
        "uploads_dir": settings.upload_dir.is_dir() and os.access(settings.upload_dir, os.W_OK),
        "outputs_dir": settings.output_dir.is_dir() and os.access(settings.output_dir, os.W_OK),
        "temp_dir": settings.temp_dir.is_dir() and os.access(settings.temp_dir, os.W_OK),
        "ffmpeg": ffmpeg_available,
        "ffprobe": ffprobe_available,
    }
    ready = all(checks.values())
    if not ready:
        response.status_code = 503
    return ReadinessResponse(ready=ready, checks=checks)
