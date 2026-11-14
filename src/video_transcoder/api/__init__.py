"""Headless FastAPI service for the Video Transcoder Docker image.

The API layer is intentionally thin: transcoding is delegated to the same
``video_transcoder.core`` engine used by the desktop application.
"""

__all__ = ["main"]
