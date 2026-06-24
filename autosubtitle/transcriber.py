from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel
from tqdm import tqdm

from autosubtitle.srt import SubtitleSegment, build_srt
from autosubtitle.translator import SubtitleTranslator


@dataclass(slots=True)
class BatchResult:
    generated: int = 0
    skipped: int = 0
    failed: int = 0


class SubtitleGenerator:
    def __init__(
        self,
        model_name: str,
        language: str | None,
        device: str,
        compute_type: str,
        beam_size: int,
        overwrite: bool,
        translate: bool,
        target_language: str,
        bilingual: bool,
        verbose: bool,
    ) -> None:
        self.language = language
        self.beam_size = beam_size
        self.overwrite = overwrite
        self.verbose = verbose
        self.translate = translate
        self.target_language = target_language
        self.bilingual = bilingual
        self.model = WhisperModel(
            model_size_or_path=model_name,
            device=device,
            compute_type=compute_type,
        )
        self.translator = (
            SubtitleTranslator(target_language=target_language, bilingual=bilingual)
            if translate
            else None
        )

    def process_files(self, video_paths: list[Path]) -> BatchResult:
        result = BatchResult()

        for video_path in tqdm(video_paths, desc="Processing videos"):
            output_path = video_path.with_suffix(".srt")
            if output_path.exists() and not self.overwrite:
                result.skipped += 1
                if self.verbose:
                    print(f"Skipped existing subtitle: {output_path}")
                continue

            try:
                self._transcribe_to_srt(video_path, output_path)
                result.generated += 1
                if self.verbose:
                    print(f"Generated subtitle: {output_path}")
            except Exception as exc:
                result.failed += 1
                print(f"Failed to process {video_path}: {exc}")

        return result

    def _transcribe_to_srt(self, video_path: Path, output_path: Path) -> None:
        segments, info = self.model.transcribe(
            str(video_path),
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )

        subtitle_segments = [
            SubtitleSegment(start=segment.start, end=segment.end, text=segment.text)
            for segment in segments
        ]
        if self.translator is not None:
            subtitle_segments = self.translator.translate_segments(
                subtitle_segments,
                source_language=info.language,
            )
        output_path.write_text(build_srt(subtitle_segments), encoding="utf-8")
