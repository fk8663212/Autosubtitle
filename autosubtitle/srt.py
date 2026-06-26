from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class SubtitleSegment:
    start: float
    end: float
    text: str


_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def parse_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def format_timestamp(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def parse_srt(content: str) -> list[SubtitleSegment]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    segments: list[SubtitleSegment] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = [line.strip("\ufeff") for line in block.split("\n")]
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if len(lines) < 2:
            continue

        match = _TIMESTAMP_PATTERN.match(lines[0].strip())
        if match is None:
            continue

        text = "\n".join(line.strip() for line in lines[1:]).strip()
        if not text:
            continue

        segments.append(
            SubtitleSegment(
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text=text,
            )
        )

    return segments


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
