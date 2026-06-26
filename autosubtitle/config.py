from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


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
    if not str(input_dir).strip():
        raise ValueError("paths.input_dir cannot be empty")
    if not str(output_dir).strip():
        raise ValueError("paths.output_dir cannot be empty")

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
    if batch_size < 1:
        raise ValueError("translation.batch_size must be at least 1")

    timeout_seconds = float(translation.get("timeout_seconds", 120))
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
