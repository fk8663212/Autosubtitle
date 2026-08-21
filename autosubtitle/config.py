from __future__ import annotations

import os
import tomllib
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
        return cls(
            state_dir=state_dir,
            upload_dir=upload_dir,
            allowed_roots=_env_paths("AUTOSUB_ALLOWED_ROOTS", upload_dir),
            model=os.getenv("AUTOSUB_MODEL", "base"),
            language=os.getenv("AUTOSUB_LANGUAGE") or None,
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


@dataclass(frozen=True, slots=True)
class PathsConfig:
    input_dir: Path
    output_dir: Path


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    model: str
    base_url: str
    api_key_env: str


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    mode: str
    target_language: str
    bilingual: bool
    batch_size: int
    timeout_seconds: float
    api: EndpointConfig
    local: EndpointConfig

    @property
    def endpoint(self) -> EndpointConfig:
        return self.api if self.mode == "api" else self.local


DEFAULT_INPUT_DIR = Path("videos")
DEFAULT_OUTPUT_DIR = Path("videos")


def load_paths_config(path: Path) -> PathsConfig:
    data = _load_config_data(path, allow_missing=True)
    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("paths must be a TOML table")

    input_dir = Path(str(paths.get("input_dir", DEFAULT_INPUT_DIR)))
    output_dir = Path(str(paths.get("output_dir", DEFAULT_OUTPUT_DIR)))
    if not str(input_dir).strip() or not str(output_dir).strip():
        raise ValueError("paths.input_dir and paths.output_dir cannot be empty")
    return PathsConfig(input_dir=input_dir, output_dir=output_dir)


def load_translation_config(path: Path) -> TranslationConfig:
    data = _load_config_data(path, allow_missing=False)
    translation = data.get("translation", {})
    if not isinstance(translation, dict):
        raise ValueError("translation must be a TOML table")
    mode = str(translation.get("mode", "local")).lower()
    if mode not in {"api", "local"}:
        raise ValueError("translation.mode must be 'api' or 'local'")

    batch_size = int(translation.get("batch_size", 20))
    timeout_seconds = float(translation.get("timeout_seconds", 120))
    if batch_size < 1:
        raise ValueError("translation.batch_size must be at least 1")
    if timeout_seconds <= 0:
        raise ValueError("translation.timeout_seconds must be greater than 0")

    return TranslationConfig(
        mode=mode,
        target_language=str(translation.get("target_language", "zh-TW")),
        bilingual=bool(translation.get("bilingual", False)),
        batch_size=batch_size,
        timeout_seconds=timeout_seconds,
        api=_load_endpoint(translation, "api", "https://api.openai.com/v1"),
        local=_load_endpoint(translation, "local", "http://127.0.0.1:11434/v1"),
    )


def _load_config_data(path: Path, allow_missing: bool) -> dict[str, object]:
    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except FileNotFoundError as exc:
        if allow_missing:
            return {}
        raise ValueError(f"Config file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML config: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a TOML table")
    return data


def _load_endpoint(
    translation: dict[str, object],
    name: str,
    default_base_url: str,
) -> EndpointConfig:
    raw_endpoint = translation.get(name, {})
    if not isinstance(raw_endpoint, dict):
        raise ValueError(f"translation.{name} must be a TOML table")
    model = str(raw_endpoint.get("model", "")).strip()
    if not model:
        raise ValueError(f"translation.{name}.model cannot be empty")
    return EndpointConfig(
        model=model,
        base_url=str(raw_endpoint.get("base_url", default_base_url)).rstrip("/"),
        api_key_env=str(raw_endpoint.get("api_key_env", "")).strip(),
    )
