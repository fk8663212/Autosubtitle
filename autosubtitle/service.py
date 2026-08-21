from __future__ import annotations

import logging
import gc
import threading
import time
from pathlib import Path

from autosubtitle.config import Settings
from autosubtitle.storage import Store
from autosubtitle.video_scan import SUPPORTED_EXTENSIONS, collect_video_files


LOGGER = logging.getLogger(__name__)


class SubtitleWorker(threading.Thread):
    def __init__(self, store: Store, settings: Settings, stop_event: threading.Event) -> None:
        super().__init__(name="subtitle-worker", daemon=True)
        self.store = store
        self.settings = settings
        self.stop_event = stop_event
        self.model_loaded = False
        self.current_job_id: int | None = None
        self._generator = None
        self._generator_signature: tuple[object, ...] | None = None

    def run(self) -> None:
        while not self.stop_event.is_set():
            job = self.store.claim_next_job()
            if job is None:
                self.stop_event.wait(1)
                continue

            self.current_job_id = job.id
            try:
                generator = self._get_generator(self.store.get_settings())
                generator.process_file(Path(job.input_path), Path(job.output_path))
            except Exception as exc:
                LOGGER.exception("Subtitle job %s failed", job.id)
                self.store.finish_job(job.id, "failed", str(exc))
            else:
                self.store.finish_job(job.id, "completed")
            finally:
                self.current_job_id = None

    def _get_generator(self, options: dict[str, object]):
        signature_keys = (
            "model",
            "language",
            "device",
            "compute_type",
            "beam_size",
            "overwrite",
            "translate",
            "translation_provider",
            "target_language",
            "llm_endpoint",
            "llm_model",
            "llm_api_key",
            "bilingual",
        )
        signature = tuple(options.get(key) for key in signature_keys)
        if self._generator is None or signature != self._generator_signature:
            from autosubtitle.transcriber import SubtitleGenerator

            self._generator = None
            self.model_loaded = False
            gc.collect()
            self._generator = SubtitleGenerator(
                model_name=str(options["model"]),
                language=options["language"] or None,
                device=str(options["device"]),
                compute_type=str(options["compute_type"]),
                beam_size=int(options["beam_size"]),
                overwrite=bool(options["overwrite"]),
                translate=bool(options["translate"]),
                translation_provider=str(options["translation_provider"]),
                target_language=str(options["target_language"]),
                llm_endpoint=options["llm_endpoint"] or None,
                llm_model=options["llm_model"] or None,
                llm_api_key=options["llm_api_key"] or None,
                bilingual=bool(options["bilingual"]),
                verbose=False,
            )
            self._generator_signature = signature
            self.model_loaded = True
        return self._generator


class FolderScanner(threading.Thread):
    def __init__(self, store: Store, settings: Settings, stop_event: threading.Event) -> None:
        super().__init__(name="folder-scanner", daemon=True)
        self.store = store
        self.settings = settings
        self.stop_event = stop_event
        self._observed: dict[Path, tuple[int, int, float]] = {}

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.scan_once()
            except Exception:
                LOGGER.exception("Watch-folder scan failed")
            self.stop_event.wait(self.settings.scan_interval)

    def scan_once(self) -> None:
        current_paths: set[Path] = set()
        now = time.monotonic()
        for folder in self.store.list_watch_folders():
            root = Path(folder.path)
            if not root.is_dir():
                continue
            for video_path in collect_video_files(root, recursive=folder.recursive):
                current_paths.add(video_path)
                if video_path.with_suffix(".srt").exists() and not self.settings.overwrite:
                    continue
                try:
                    stat = video_path.stat()
                except OSError:
                    continue
                signature = (stat.st_size, stat.st_mtime_ns)
                previous = self._observed.get(video_path)
                if previous is None or previous[:2] != signature:
                    self._observed[video_path] = (*signature, now)
                    continue
                if now - previous[2] < self.settings.stable_seconds:
                    continue
                try:
                    self.store.enqueue(video_path, source="watch")
                except (OSError, ValueError) as exc:
                    LOGGER.warning("Could not enqueue watched file %s: %s", video_path, exc)

        for stale_path in self._observed.keys() - current_paths:
            self._observed.pop(stale_path, None)


class ApplicationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = Store(settings.database_path)
        self.stop_event = threading.Event()
        self.worker = SubtitleWorker(self.store, settings, self.stop_event)
        self.scanner = FolderScanner(self.store, settings, self.stop_event)

    def start(self) -> None:
        self.settings.prepare_directories()
        self.store.initialize()
        self.store.seed_settings(self.settings.runtime_defaults())
        self.worker.start()
        self.scanner.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.worker.join(timeout=10)
        self.scanner.join(timeout=10)

    def status(self) -> dict[str, object]:
        runtime = self.store.get_settings()
        return {
            "worker_alive": self.worker.is_alive(),
            "scanner_alive": self.scanner.is_alive(),
            "model_loaded": self.worker.model_loaded,
            "current_job_id": self.worker.current_job_id,
            "device": runtime["device"],
            "model": runtime["model"],
            "translation_enabled": runtime["translate"],
            "translation_provider": runtime["translation_provider"],
            "target_language": runtime["target_language"],
            "allowed_roots": [str(path) for path in self.settings.allowed_roots],
        }


def is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS
