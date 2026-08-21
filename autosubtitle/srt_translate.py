from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tqdm import tqdm

from autosubtitle.pathing import build_subtitle_output_path
from autosubtitle.srt import SubtitleSegment, build_srt, parse_srt


class SegmentTranslator(Protocol):
    def translate_segments(
        self,
        segments: list[SubtitleSegment],
        source_language: str | None,
    ) -> list[SubtitleSegment]:
        ...


@dataclass(slots=True)
class SrtTranslationResult:
    generated: int = 0
    skipped: int = 0
    failed: int = 0


def collect_srt_files(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".srt" else []

    iterator = input_path.rglob("*.srt") if recursive else input_path.glob("*.srt")
    return sorted(path for path in iterator if path.is_file())


class ExistingSrtTranslator:
    def __init__(
        self,
        translator: SegmentTranslator,
        overwrite: bool,
        source_language: str | None,
        target_language: str,
        verbose: bool,
        input_root: Path,
        output_root: Path,
    ) -> None:
        self.translator = translator
        self.overwrite = overwrite
        self.source_language = source_language
        self.target_language = target_language
        self.verbose = verbose
        self.input_root = input_root
        self.output_root = output_root

    def process_files(self, srt_paths: list[Path]) -> SrtTranslationResult:
        result = SrtTranslationResult()

        for srt_path in tqdm(srt_paths, desc="Translating SRT files"):
            output_path = self._output_path(srt_path)
            if output_path.exists() and not self.overwrite:
                result.skipped += 1
                if self.verbose:
                    print(f"Skipped existing translation: {output_path}")
                continue

            try:
                self._translate_srt(srt_path, output_path)
                result.generated += 1
                if self.verbose:
                    print(f"Generated translated subtitle: {output_path}")
            except Exception as exc:
                result.failed += 1
                print(f"Failed to translate {srt_path}: {exc}")

        return result

    def _output_path(self, srt_path: Path) -> Path:
        return build_subtitle_output_path(
            srt_path,
            input_root=self.input_root,
            output_root=self.output_root,
            extra_suffix=f".{self.target_language}",
        )

    def _translate_srt(self, srt_path: Path, output_path: Path) -> None:
        segments = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
        if not segments:
            raise ValueError("No valid subtitle blocks found")

        translated_segments = self.translator.translate_segments(
            segments,
            source_language=self.source_language,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            build_srt(translated_segments),
            encoding="utf-8-sig",
            newline="\r\n",
        )
