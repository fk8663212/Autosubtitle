from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SubtitleSegment:
    start: float
    end: float
    text: str


def format_timestamp(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def build_srt(segments: list[SubtitleSegment]) -> str:
    blocks: list[str] = []
    subtitle_index = 1
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(subtitle_index),
                    f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}",
                    text,
                ]
            )
        )
        subtitle_index += 1
    return "\n\n".join(blocks) + ("\n" if blocks else "")
