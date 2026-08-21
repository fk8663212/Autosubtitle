from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_paths(name: str, default: Path) -> tuple[Path, ...]:
    raw_value = os.getenv(name)
    values = raw_value.split(os.pathsep) if raw_value else [str(default)]
    return tuple(Path(value).expanduser().resolve() for value in values if value)


@dataclass(frozen=True, slots=True)
class Settings:
    state_dir: Path
    upload_dir: Path
    allowed_roots: tuple[Path, ...]
    model: str
    language: str | None
    device: str
    compute_type: str
    beam_size: int
    translate: bool
    translation_provider: str
    target_language: str
    llm_endpoint: str | None
    llm_model: str | None
    llm_api_key: str | None
    bilingual: bool
    overwrite: bool
    scan_interval: float
    stable_seconds: float

    @property
    def database_path(self) -> Path:
        return self.state_dir / "autosubtitle.db"

    @classmethod
    def from_env(cls) -> "Settings":
        state_dir = Path(os.getenv("AUTOSUB_STATE_DIR", "./state")).expanduser().resolve()
        upload_dir = Path(
            os.getenv("AUTOSUB_UPLOAD_DIR", str(state_dir / "uploads"))
        ).expanduser().resolve()
        language = os.getenv("AUTOSUB_LANGUAGE") or None
        return cls(
            state_dir=state_dir,
            upload_dir=upload_dir,
            allowed_roots=_env_paths("AUTOSUB_ALLOWED_ROOTS", upload_dir),
            model=os.getenv("AUTOSUB_MODEL", "base"),
            language=language,
            device=os.getenv("AUTOSUB_DEVICE", "auto"),
            compute_type=os.getenv("AUTOSUB_COMPUTE_TYPE", "auto"),
            beam_size=int(os.getenv("AUTOSUB_BEAM_SIZE", "5")),
            translate=_env_bool("AUTOSUB_TRANSLATE", False),
            translation_provider=os.getenv("AUTOSUB_TRANSLATION_PROVIDER", "google"),
            target_language=os.getenv("AUTOSUB_TARGET_LANGUAGE", "zh-TW"),
            llm_endpoint=os.getenv("AUTOSUB_LLM_ENDPOINT") or None,
            llm_model=os.getenv("AUTOSUB_LLM_MODEL") or None,
            llm_api_key=os.getenv("AUTOSUB_LLM_API_KEY") or None,
            bilingual=_env_bool("AUTOSUB_BILINGUAL", False),
            overwrite=_env_bool("AUTOSUB_OVERWRITE", False),
            scan_interval=float(os.getenv("AUTOSUB_SCAN_INTERVAL", "10")),
            stable_seconds=float(os.getenv("AUTOSUB_STABLE_SECONDS", "30")),
        )

    def prepare_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def runtime_defaults(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "language": self.language,
            "device": self.device,
            "compute_type": self.compute_type,
            "beam_size": self.beam_size,
            "translate": self.translate,
            "translation_provider": self.translation_provider,
            "target_language": self.target_language,
            "llm_endpoint": self.llm_endpoint,
            "llm_model": self.llm_model,
            "llm_api_key": self.llm_api_key,
            "bilingual": self.bilingual,
            "overwrite": self.overwrite,
        }

    def validate_path(self, path: Path, *, require_directory: bool = False) -> Path:
        resolved = path.expanduser().resolve()
        if not any(resolved == root or resolved.is_relative_to(root) for root in self.allowed_roots):
            roots = ", ".join(str(root) for root in self.allowed_roots)
            raise ValueError(f"Path is outside AUTOSUB_ALLOWED_ROOTS: {roots}")
        if not resolved.exists():
            raise ValueError(f"Path does not exist: {resolved}")
        if require_directory and not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")
        if not require_directory and not resolved.is_file():
            raise ValueError(f"Path is not a file: {resolved}")
        return resolved
