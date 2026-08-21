from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autosubtitle.config import Settings


def make_settings(root: Path) -> Settings:
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
        overwrite=False,
        scan_interval=1,
        stable_seconds=0,
    )


class SettingsTest(unittest.TestCase):
    def test_validate_path_accepts_allowed_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.touch()
            self.assertEqual(make_settings(root).validate_path(video), video.resolve())

    def test_validate_path_rejects_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
            path = Path(other) / "video.mp4"
            path.touch()
            with self.assertRaisesRegex(ValueError, "outside"):
                make_settings(Path(allowed)).validate_path(path)


if __name__ == "__main__":
    unittest.main()
