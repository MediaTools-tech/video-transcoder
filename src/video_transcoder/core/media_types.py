"""Shared policy for accepted video input files."""

from pathlib import Path
from typing import Union

VIDEO_INPUT_EXTENSIONS = frozenset(
    {
        ".3g2",
        ".3gp",
        ".apng",
        ".asf",
        ".avi",
        ".divx",
        ".dv",
        ".f4v",
        ".flv",
        ".gif",
        ".m1v",
        ".m2p",
        ".m2ts",
        ".m2v",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpe",
        ".mpeg",
        ".mpg",
        ".mpv",
        ".mts",
        ".mxf",
        ".ogg",
        ".ogm",
        ".ogv",
        ".rm",
        ".rmvb",
        ".ts",
        ".vob",
        ".webm",
        ".webp",
        ".wmv",
        ".y4m",
    }
)

VIDEO_INPUT_FILE_TYPES = (
    ("Video files", " ".join(f"*{extension}" for extension in sorted(VIDEO_INPUT_EXTENSIONS))),
)


def is_supported_video_extension(extension: str) -> bool:
    """Return whether ``extension`` is in the supported video input policy."""
    if not extension:
        return False
    suffix = extension.lower()
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix in VIDEO_INPUT_EXTENSIONS


def is_supported_video_path(path: Union[str, Path]) -> bool:
    """Return whether a path has a supported video input extension."""
    return is_supported_video_extension(Path(path).suffix)


def format_supported_video_extensions(separator: str = ", ") -> str:
    """Return the supported extensions in a stable, human-readable order."""
    return separator.join(sorted(VIDEO_INPUT_EXTENSIONS))
