from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VideoCodec(str, Enum):
    DEFAULT = "default"
    H264 = "h264"
    H265 = "h265"
    AV1 = "av1"
    VP9 = "vp9"


class Resolution(str, Enum):
    DEFAULT = "default"
    AUTO = "auto"
    P480 = "480p"
    P576 = "576p"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"
    P4K = "4k"


class Sharpening(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MEDIUM = "medium"
    STRONG = "strong"
    ADAPTIVE = "adaptive"


class Container(str, Enum):
    DEFAULT = "default"
    MP4 = "mp4"
    MKV = "mkv"
    AVI = "avi"
    WEBM = "webm"
    MOV = "mov"


class AudioCodec(str, Enum):
    DEFAULT = "default"
    COPY = "copy"
    AAC = "aac"
    MP3 = "mp3"
    OPUS = "opus"
    AC3 = "ac3"
    FLAC = "flac"
    VORBIS = "vorbis"


class TranscodingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_codec: VideoCodec = VideoCodec.DEFAULT
    resolution: Resolution = Resolution.DEFAULT
    sharpening: Sharpening = Sharpening.NONE
    container: Container = Container.DEFAULT
    audio_codec: AudioCodec = AudioCodec.DEFAULT
    crf: int = Field(default=23, ge=0, le=51)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    filename: str
    status: str
    progress: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    input_path: str
    output_path: Optional[str] = None
    file_size_mb: Optional[float] = None
    options: Optional[TranscodingOptions] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    ffmpeg_available: bool
    ffprobe_available: bool
    ffmpeg_version: Optional[str] = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, bool]
