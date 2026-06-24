from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}


def collect_video_files(input_dir: Path, recursive: bool) -> list[Path]:
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    files = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)
