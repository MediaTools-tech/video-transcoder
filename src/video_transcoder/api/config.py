from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the headless API/Docker service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Video Transcoder"
    debug: bool = False

    upload_dir: Path = Path("storage/uploads")
    temp_dir: Path = Path("storage/temp")
    output_dir: Path = Path("storage/outputs")
    max_concurrent_jobs: int = Field(default=2, ge=1)

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    cors_origins: str = "*"
    frontend_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent / "frontend"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["*"]


settings = Settings()
