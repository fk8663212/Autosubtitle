from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
import whisper
from tqdm import tqdm

from autosubtitle.config import TranslationConfig
from autosubtitle.pathing import build_subtitle_output_path
from autosubtitle.srt import SubtitleSegment, build_srt, parse_srt
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
        translation_provider: str = "google",
        llm_endpoint: str | None = None,
        llm_model: str | None = None,
        llm_api_key: str | None = None,
        translation_config: TranslationConfig | None = None,
        input_root: Path | None = None,
        output_root: Path | None = None,
    ) -> None:
        self.device = self._resolve_device(device)
        self.fp16 = self._resolve_fp16(compute_type, self.device)
        self.language = language
        self.beam_size = beam_size
        self.overwrite = overwrite
        self.verbose = verbose
        self.model_name = model_name
        self.model = None
        self.input_root = input_root
        self.output_root = output_root
        self.translation_target_language = (
            target_language
            or (translation_config.target_language if translation_config else "zh-TW")
        )
        self.translator = (
            SubtitleTranslator(
                target_language=target_language,
                bilingual=bilingual,
                provider=translation_provider,
                endpoint=llm_endpoint,
                model=llm_model,
                api_key=llm_api_key,
                config=translation_config,
            )
            if translate
            else None
        )

    def process_files(self, video_paths: list[Path]) -> BatchResult:
        result = BatchResult()
        for video_path in tqdm(video_paths, desc="Processing videos"):
            source_srt_path = video_path.with_suffix(".srt")
            output_path = self._output_path(video_path)
            try:
                if self.translator is not None and source_srt_path.exists():
                    translated_output = self._translated_srt_path(source_srt_path)
                    if translated_output.exists() and not self.overwrite:
                        result.skipped += 1
                        continue
                    self._translate_existing_srt(source_srt_path, translated_output)
                    result.generated += 1
                    continue

                if output_path.exists() and not self.overwrite:
                    result.skipped += 1
                    continue
                self.process_file(video_path, output_path)
                result.generated += 1
            except Exception as exc:
                result.failed += 1
                print(f"Failed to process {video_path}: {exc}")
        return result

    def process_file(
        self,
        video_path: Path,
        output_path: Path | None = None,
    ) -> Path:
        output_path = output_path or self._output_path(video_path)
        if output_path.exists() and not self.overwrite:
            raise FileExistsError(f"Subtitle already exists: {output_path}")
        self._transcribe_to_srt(video_path, output_path)
        if self.verbose:
            print(f"Generated subtitle: {output_path}")
        return output_path

    def _output_path(self, source_path: Path, extra_suffix: str = "") -> Path:
        if self.input_root is None or self.output_root is None:
            return source_path.with_name(f"{source_path.stem}{extra_suffix}.srt")
        return build_subtitle_output_path(
            source_path,
            input_root=self.input_root,
            output_root=self.output_root,
            extra_suffix=extra_suffix,
        )

    def _translated_srt_path(self, source_srt_path: Path) -> Path:
        return self._output_path(
            source_srt_path,
            extra_suffix=f".{self.translation_target_language}",
        )

    def _translate_existing_srt(self, source_srt_path: Path, output_path: Path) -> None:
        if self.translator is None:
            raise ValueError("Translation is not enabled")
        segments = parse_srt(source_srt_path.read_text(encoding="utf-8-sig"))
        if not segments:
            raise ValueError("No valid subtitle blocks found")
        translated = self.translator.translate_segments(segments, self.language)
        self._write_srt(output_path, translated)

    def _transcribe_to_srt(self, video_path: Path, output_path: Path) -> None:
        if self.model is None:
            self.model = whisper.load_model(self.model_name, device=self.device)
        transcription = self.model.transcribe(
            str(video_path),
            language=self.language,
            beam_size=self.beam_size,
            fp16=self.fp16,
            verbose=self.verbose,
        )
        segments = [
            SubtitleSegment(
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]),
            )
            for segment in transcription["segments"]
        ]
        if self.translator is not None:
            segments = self.translator.translate_segments(
                segments,
                source_language=transcription.get("language"),
            )
        self._write_srt(output_path, segments)

    @staticmethod
    def _write_srt(output_path: Path, segments: list[SubtitleSegment]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(f".{output_path.name}.tmp")
        try:
            temporary_path.write_text(build_srt(segments), encoding="utf-8-sig")
            temporary_path.replace(output_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested, but PyTorch cannot access the GPU. "
                "Use the NVIDIA container or select CPU."
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
            f"Unsupported compute type: {compute_type}. Choose auto, float16, or float32."
        )
