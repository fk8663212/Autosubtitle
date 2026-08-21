from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from autosubtitle.config import Settings
from autosubtitle.service import FolderScanner
from autosubtitle.storage import Store


def make_settings(root: Path, overwrite: bool = False) -> Settings:
    return Settings(
        state_dir=root / "state",
        upload_dir=root / "uploads",
        allowed_roots=(root,),
        model="tiny",
        language=None,
        device="cpu",
        compute_type="float32",
        beam_size=1,
        translate=False,
        translation_provider="google",
        target_language="zh-TW",
        llm_endpoint=None,
        llm_model=None,
        llm_api_key=None,
        bilingual=False,
        overwrite=overwrite,
        scan_interval=1,
        stable_seconds=0,
    )


class StoreTest(unittest.TestCase):
    def test_settings_are_seeded_once_and_can_be_updated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            settings.prepare_directories()
            store = Store(settings.database_path)
            store.initialize()

            store.seed_settings({"model": "base", "translate": False})
            store.seed_settings({"model": "large-v3", "translate": True})
            self.assertEqual(store.get_settings()["model"], "base")
            updated = store.update_settings({"model": "small", "translate": True})
            self.assertEqual(updated["model"], "small")
            self.assertTrue(updated["translate"])

    def test_enqueue_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            settings.prepare_directories()
            store = Store(settings.database_path)
            store.initialize()
            video = root / "video.mp4"
            video.write_bytes(b"video")

            first, first_created = store.enqueue(video, "manual")
            second, second_created = store.enqueue(video, "watch")

            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(first.id, second.id)

    def test_output_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            settings.prepare_directories()
            store = Store(settings.database_path)
            store.initialize()
            (root / "movie.mp4").write_bytes(b"mp4")
            (root / "movie.mkv").write_bytes(b"mkv")

            store.enqueue(root / "movie.mp4", "manual")
            with self.assertRaisesRegex(ValueError, "collision"):
                store.enqueue(root / "movie.mkv", "manual")

    def test_scanner_waits_for_a_stable_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            settings.prepare_directories()
            store = Store(settings.database_path)
            store.initialize()
            store.add_watch_folder(root, recursive=False)
            (root / "lesson.mp4").write_bytes(b"video")
            scanner = FolderScanner(store, settings, threading.Event())

            scanner.scan_once()
            self.assertEqual(store.list_jobs(), [])
            scanner.scan_once()
            self.assertEqual(len(store.list_jobs()), 1)


if __name__ == "__main__":
    unittest.main()
