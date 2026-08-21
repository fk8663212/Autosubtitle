from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from autosubtitle.config import Settings
from autosubtitle.web import (
    GlobalSettingsRequest,
    PathJobRequest,
    WatchFolderRequest,
    create_app,
)


def make_settings(root: Path) -> Settings:
    return Settings(
        state_dir=root / "state",
        upload_dir=root / "uploads",
        allowed_roots=(root / "media", root / "uploads"),
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
        overwrite=False,
        scan_interval=60,
        stable_seconds=60,
    )


class WebTest(unittest.TestCase):
    def test_routes_use_service_and_enforce_path_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "media").mkdir()
            app = create_app(make_settings(root))
            def route(path: str, method: str = "GET"):
                return next(
                    item.endpoint
                    for item in app.routes
                    if item.path == path
                    and hasattr(item, "methods")
                    and method in item.methods
                )

            service = app.state.service
            service.start()
            try:
                self.assertTrue(service.status()["worker_alive"])
                self.assertTrue(route("/api/status")()["scanner_alive"])
                self.assertEqual(Path(route("/")().path).name, "index.html")

                watch = route("/api/watch-folders", "POST")(
                    WatchFolderRequest(path=str(root / "media"), recursive=True)
                )
                self.assertTrue(watch["recursive"])

                with self.assertRaises(HTTPException) as rejected:
                    route("/api/jobs/path", "POST")(PathJobRequest(path="/etc/passwd"))
                self.assertEqual(rejected.exception.status_code, 400)

                service.store.update_settings({"llm_api_key": "existing-secret"})
                saved = route("/api/settings", "PUT")(
                    GlobalSettingsRequest(
                        model="small",
                        language="en",
                        device="auto",
                        compute_type="auto",
                        beam_size=5,
                        translate=True,
                        translation_provider="google",
                        target_language="zh-TW",
                        llm_endpoint=None,
                        llm_model=None,
                        llm_api_key=None,
                        bilingual=True,
                        overwrite=False,
                    )
                )
                self.assertEqual(saved["model"], "small")
                self.assertTrue(saved["llm_api_key_configured"])
                self.assertNotIn("llm_api_key", saved)
                self.assertEqual(
                    service.store.get_settings()["llm_api_key"], "existing-secret"
                )

                service.stop()
                video = root / "media" / "lesson.mp4"
                video.write_bytes(b"video")
                job, _ = service.store.enqueue(video, "manual")
                subtitle = root / "media" / "lesson.srt"
                subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
                service.store.finish_job(job.id, "completed")
                response = route("/api/jobs/{job_id}/download")(job.id)
                self.assertEqual(Path(response.path), subtitle)
                self.assertEqual(response.filename, "lesson.srt")
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
