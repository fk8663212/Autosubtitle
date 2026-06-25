from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
import whisper
from tqdm import tqdm

from autosubtitle.config import TranslationConfig
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
        translation_config: TranslationConfig | None,
        target_language: str | None,
        bilingual: bool | None,
        verbose: bool,
    ) -> None:
        device = self._resolve_device(device)
        self.fp16 = self._resolve_fp16(compute_type, device)

        self.language = language
        self.beam_size = beam_size
        self.overwrite = overwrite
        self.verbose = verbose
        self.translate = translate
        if translate and translation_config is None:
            raise ValueError("Translation config is required when translation is enabled")
        self.model = whisper.load_model(model_name, device=device)
        self.translator = (
            SubtitleTranslator(
                config=translation_config,
                target_language=target_language,
                bilingual=bilingual,
            )
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
        transcription = self.model.transcribe(
            str(video_path),
            language=self.language,
            beam_size=self.beam_size,
            fp16=self.fp16,
            verbose=self.verbose,
        )

        subtitle_segments = [
            SubtitleSegment(
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]),
            )
            for segment in transcription["segments"]
        ]
        if self.translator is not None:
            subtitle_segments = self.translator.translate_segments(
                subtitle_segments,
                source_language=transcription.get("language"),
            )
        output_path.write_text(
            build_srt(subtitle_segments),
            encoding="utf-8-sig",
            newline="\r\n",
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested, but PyTorch cannot access the GPU. "
                "Run this project in the NVIDIA PyTorch container described "
                "in GB10_DGX_SPARK.md, or use --device cpu."
            )
        return device

    @staticmethod
    def _resolve_fp16(compute_type: str, device: str) -> bool:
        if compute_type == "auto":
            return device == "cuda"
        if compute_type == "float16":
            if device != "cuda":
                raise ValueError("float16 inference requires CUDA")
            return True
        if compute_type == "float32":
            return False
        raise ValueError(
            "Unsupported compute type for OpenAI Whisper: "
            f"{compute_type}. Choose auto, float16, or float32."
        )
