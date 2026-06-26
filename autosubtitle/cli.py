from __future__ import annotations

import argparse
from pathlib import Path

from autosubtitle.config import TranslationConfig, load_paths_config, load_translation_config
from autosubtitle.video_scan import collect_video_files
from autosubtitle.watcher import watch_video_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or translate external .srt subtitles."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Folder containing video files, or an .srt file with --translate-srt (default: config.toml paths.input_dir)",
    )
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
        "--watch",
        action="store_true",
        help="Keep watching the folder and process new or changed videos",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between folder scans in watch mode (default: 2)",
    )
    parser.add_argument(
        "--stable-seconds",
        type=float,
        default=10.0,
        help="Wait until a video is unchanged for this many seconds (default: 10)",
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
        help="Translate subtitles; existing same-name .srt files skip Whisper",
    )
    parser.add_argument(
        "--translate-srt",
        action="store_true",
        help="Translate existing .srt files without running Whisper",
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

    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than 0")
    if args.stable_seconds < 0:
        parser.error("--stable-seconds cannot be negative")
    if args.translate_srt and args.watch:
        parser.error("--translate-srt cannot be used with --watch")

    try:
        paths_config = load_paths_config(args.config)
    except ValueError as exc:
        print(f"Invalid configuration: {exc}")
        return 1

    input_dir = args.input_dir or paths_config.input_dir
    output_dir = paths_config.output_dir
    if not input_dir.exists():
        parser.error(f"Input path does not exist: {input_dir}")

    translation_config = None
    if args.translate or args.translate_srt:
        try:
            translation_config = load_translation_config(args.config)
        except ValueError as exc:
            print(f"Invalid configuration: {exc}")
            return 1

    if args.translate_srt:
        return _translate_existing_srt(args, translation_config, input_dir, output_dir)

    if not input_dir.is_dir():
        parser.error(f"Input path is not a directory: {input_dir}")

    videos = collect_video_files(input_dir, recursive=args.recursive)
    if not videos and not args.watch:
        print("No supported video files found.")
        return 0

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
            input_root=input_dir,
            output_root=output_dir,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        print(
            "Unable to initialize Whisper. For GB10 CUDA support, see "
            "GB10_DGX_SPARK.md."
        )
        print(f"Details: {exc}")
        return 1

    if args.watch:
        return _watch_folder(generator, args, input_dir)

    result = generator.process_files(videos)

    print(
        f"Finished. Generated {result.generated} subtitle file(s), "
        f"skipped {result.skipped}, failed {result.failed}."
    )
    return 0 if result.failed == 0 else 1


def _translate_existing_srt(
    args: argparse.Namespace,
    translation_config: TranslationConfig,
    input_dir: Path,
    output_dir: Path,
) -> int:
    from autosubtitle.srt_translate import ExistingSrtTranslator, collect_srt_files
    from autosubtitle.translator import SubtitleTranslator

    srt_paths = collect_srt_files(input_dir, recursive=args.recursive)
    if not srt_paths:
        print("No .srt files found.")
        return 0

    target_language = args.target_language or translation_config.target_language
    translator = SubtitleTranslator(
        config=translation_config,
        target_language=args.target_language,
        bilingual=args.bilingual,
    )
    processor = ExistingSrtTranslator(
        translator=translator,
        overwrite=args.overwrite,
        source_language=args.language,
        target_language=target_language,
        verbose=args.verbose,
        input_root=input_dir,
        output_root=output_dir,
    )
    result = processor.process_files(srt_paths)

    print(
        f"Finished. Generated {result.generated} translated subtitle file(s), "
        f"skipped {result.skipped}, failed {result.failed}."
    )
    return 0 if result.failed == 0 else 1


def _watch_folder(generator: object, args: argparse.Namespace, input_dir: Path) -> int:
    print(
        f"Watching {input_dir} for videos "
        f"(stable for {args.stable_seconds:g}s before processing)."
    )
    print("Press Ctrl+C to stop.")

    try:
        for video_path in watch_video_files(
            input_dir,
            recursive=args.recursive,
            poll_interval=args.poll_interval,
            stable_seconds=args.stable_seconds,
        ):
            print(f"Detected ready video: {video_path}")
            result = generator.process_files([video_path])
            print(
                f"Watch result. Generated {result.generated}, "
                f"skipped {result.skipped}, failed {result.failed}."
            )
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0
