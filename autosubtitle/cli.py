from __future__ import annotations

import argparse
from pathlib import Path

from autosubtitle.config import load_translation_config
from autosubtitle.video_scan import collect_video_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate external .srt subtitles for every video in a folder."
    )
    parser.add_argument("input_dir", type=Path, help="Folder containing video files")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Translation config file (default: config.toml)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subdirectories recursively",
    )
    parser.add_argument(
        "--model",
        default="base",
        help="Whisper model size, for example tiny/base/small/medium/large-v3",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code such as zh, en, ja. Omit to auto-detect.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["auto", "cpu", "cuda"],
        help="Inference device (default: cuda)",
    )
    parser.add_argument(
        "--compute-type",
        default="auto",
        choices=["auto", "float16", "float32"],
        help="PyTorch precision (default: auto; CUDA uses float16)",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam search size",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing subtitle files",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Translate subtitles after transcription (disabled by default)",
    )
    parser.add_argument(
        "--target-language",
        default=None,
        help="Override the target language from config.toml",
    )
    parser.add_argument(
        "--bilingual",
        action="store_true",
        default=None,
        help="Override config.toml and output bilingual subtitles",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each generated subtitle path",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.input_dir.exists():
        parser.error(f"Input directory does not exist: {args.input_dir}")
    if not args.input_dir.is_dir():
        parser.error(f"Input path is not a directory: {args.input_dir}")

    videos = collect_video_files(args.input_dir, recursive=args.recursive)
    if not videos:
        print("No supported video files found.")
        return 0

    translation_config = None
    if args.translate:
        try:
            translation_config = load_translation_config(args.config)
        except ValueError as exc:
            print(f"Invalid configuration: {exc}")
            return 1

    try:
        from autosubtitle.transcriber import SubtitleGenerator
    except ImportError as exc:
        print(
            "Missing dependency. Please install requirements first with: "
            "pip install -r requirements.txt"
        )
        print(f"Details: {exc}")
        return 1

    try:
        generator = SubtitleGenerator(
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            overwrite=args.overwrite,
            translate=args.translate,
            translation_config=translation_config,
            target_language=args.target_language,
            bilingual=args.bilingual,
            verbose=args.verbose,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        print(
            "Unable to initialize Whisper. For GB10 CUDA support, use the "
            "NVIDIA PyTorch container described in README.md."
        )
        print(f"Details: {exc}")
        return 1

    result = generator.process_files(videos)

    print(
        f"Finished. Generated {result.generated} subtitle file(s), "
        f"skipped {result.skipped}, failed {result.failed}."
    )
    return 0 if result.failed == 0 else 1
