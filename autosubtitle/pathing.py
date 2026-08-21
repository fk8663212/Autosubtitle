from __future__ import annotations

from pathlib import Path


def build_subtitle_output_path(
    source_path: Path,
    input_root: Path,
    output_root: Path,
    extra_suffix: str = "",
) -> Path:
    try:
        relative_path = source_path.relative_to(input_root)
    except ValueError:
        relative_path = Path(source_path.name)

    subtitle_name = f"{relative_path.stem}{extra_suffix}.srt"
    return output_root / relative_path.parent / subtitle_name
