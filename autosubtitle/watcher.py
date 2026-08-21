from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from autosubtitle.video_scan import collect_video_files


@dataclass(slots=True)
class _FileState:
    signature: tuple[int, int]
    stable_since: float


def watch_video_files(
    input_dir: Path,
    recursive: bool,
    poll_interval: float,
    stable_seconds: float,
) -> Iterator[Path]:
    """Yield new or changed videos after their size and mtime stop changing."""
    states: dict[Path, _FileState] = {}
    handled: dict[Path, tuple[int, int]] = {}

    while True:
        now = time.monotonic()
        current_paths = set(collect_video_files(input_dir, recursive=recursive))

        for path in sorted(current_paths):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue

            signature = (stat.st_size, stat.st_mtime_ns)
            if stat.st_size == 0:
                continue
            state = states.get(path)
            if state is None or state.signature != signature:
                states[path] = _FileState(signature=signature, stable_since=now)
                continue

            if (
                signature != handled.get(path)
                and now - state.stable_since >= stable_seconds
            ):
                handled[path] = signature
                yield path

        for removed_path in states.keys() - current_paths:
            states.pop(removed_path, None)
            handled.pop(removed_path, None)

        time.sleep(poll_interval)
