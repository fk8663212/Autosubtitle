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
    parser.add_argument("input_dir", nargs="?", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--stable-seconds", type=float, default=10.0)
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument(
        "--compute-type",
        default="auto",
        choices=["auto", "float16", "float32"],
    )
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--translate", action="store_true")
    parser.add_argument("--translate-srt", action="store_true")
    parser.add_argument("--target-language", default=None)
    parser.add_argument(
        "--translation-provider",
        choices=["google", "ollama", "openai"],
        default=None,
    )
    parser.add_argument("--llm-endpoint", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--bilingual", action="store_true", default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than 0")
    if args.stable_seconds < 0:
        parser.error("--stable-seconds cannot be negative")
    if args.beam_size < 1:
        parser.error("--beam-size must be at least 1")
    if args.translate_srt and args.watch:
        parser.error("--translate-srt cannot be used with --watch")

    try:
        paths_config = load_paths_config(args.config)
    except ValueError as exc:
        print(f"Invalid path configuration: {exc}")
        return 1
    input_dir = args.input_dir or paths_config.input_dir
    output_dir = paths_config.output_dir
    if not input_dir.exists():
        parser.error(f"Input path does not exist: {input_dir}")

    translation_config = _load_optional_translation_config(args)
    if isinstance(translation_config, str):
        print(translation_config)
        return 1
    target_language = (
        args.target_language
        or (translation_config.target_language if translation_config else "zh-TW")
    )
    bilingual = (
        translation_config.bilingual
        if args.bilingual is None and translation_config
        else bool(args.bilingual)
    )

    if args.translate_srt:
        return _translate_existing_srt(
            args,
            translation_config,
            input_dir,
            output_dir,
            target_language,
            bilingual,
        )
    if not input_dir.is_dir():
        parser.error(f"Input path is not a directory: {input_dir}")

    videos = collect_video_files(input_dir, recursive=args.recursive)
    if not videos and not args.watch:
        print("No supported video files found.")
        return 0

    try:
        from autosubtitle.transcriber import SubtitleGenerator

        generator = SubtitleGenerator(
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            overwrite=args.overwrite,
            translate=args.translate,
            target_language=target_language,
            bilingual=bilingual,
            verbose=args.verbose,
            translation_provider=args.translation_provider or "google",
            llm_endpoint=args.llm_endpoint,
            llm_model=args.llm_model,
            llm_api_key=args.llm_api_key,
            translation_config=translation_config,
            input_root=input_dir,
            output_root=output_dir,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        print(f"Unable to initialize Whisper or translation: {exc}")
        return 1

    if args.watch:
        return _watch_folder(generator, args, input_dir)
    result = generator.process_files(videos)
    print(
        f"Finished. Generated {result.generated} subtitle file(s), "
        f"skipped {result.skipped}, failed {result.failed}."
    )
    return 0 if result.failed == 0 else 1


def _load_optional_translation_config(
    args: argparse.Namespace,
) -> TranslationConfig | str | None:
    if not (args.translate or args.translate_srt):
        return None
    if args.translation_provider is not None or not args.config.exists():
        if (args.translation_provider or "google") != "google" and not args.llm_model:
            return "--llm-model is required for Ollama or OpenAI translation"
        return None
    try:
        return load_translation_config(args.config)
    except ValueError as exc:
        return f"Invalid translation configuration: {exc}"


def _translate_existing_srt(
    args: argparse.Namespace,
    translation_config: TranslationConfig | None,
    input_dir: Path,
    output_dir: Path,
    target_language: str,
    bilingual: bool,
) -> int:
    from autosubtitle.srt_translate import ExistingSrtTranslator, collect_srt_files
    from autosubtitle.translator import SubtitleTranslator

    srt_paths = collect_srt_files(input_dir, recursive=args.recursive)
    if not srt_paths:
        print("No .srt files found.")
        return 0
    translator = SubtitleTranslator(
        target_language=target_language,
        bilingual=bilingual,
        provider=args.translation_provider or "google",
        endpoint=args.llm_endpoint,
        model=args.llm_model,
        api_key=args.llm_api_key,
        config=translation_config,
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
    print(f"Watching {input_dir}; files must be stable for {args.stable_seconds:g}s.")
    try:
        for video_path in watch_video_files(
            input_dir,
            recursive=args.recursive,
            poll_interval=args.poll_interval,
            stable_seconds=args.stable_seconds,
        ):
            result = generator.process_files([video_path])
            print(
                f"Watch result. Generated {result.generated}, "
                f"skipped {result.skipped}, failed {result.failed}."
            )
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0
