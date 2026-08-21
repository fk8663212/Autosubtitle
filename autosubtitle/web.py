from __future__ import annotations

import argparse
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator, Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from autosubtitle.config import Settings
from autosubtitle.service import ApplicationService, is_supported_video


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")


class PathJobRequest(BaseModel):
    path: str


class WatchFolderRequest(BaseModel):
    path: str
    recursive: bool = False


class GlobalSettingsRequest(BaseModel):
    model: Literal[
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large",
        "large-v1",
        "large-v2",
        "large-v3",
        "turbo",
    ]
    language: str | None = None
    device: Literal["auto", "cpu", "cuda"]
    compute_type: Literal["auto", "float16", "float32"]
    beam_size: int = Field(ge=1, le=20)
    translate: bool
    translation_provider: Literal["google", "ollama", "openai"]
    target_language: str = Field(min_length=2, max_length=20)
    llm_endpoint: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    bilingual: bool
    overwrite: bool

    @field_validator("language", "llm_endpoint", "llm_model", "llm_api_key", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("language", "target_language", "llm_endpoint", "llm_model")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def validate_translation_backend(self) -> "GlobalSettingsRequest":
        if self.device == "cpu" and self.compute_type == "float16":
            raise ValueError("CPU mode cannot use FP16 compute type")
        if self.translate and self.translation_provider in {"ollama", "openai"}:
            if not self.llm_model:
                raise ValueError("Ollama or OpenAI translation requires an LLM model")
            if self.translation_provider == "openai" and not self.llm_endpoint:
                raise ValueError("OpenAI translation requires a chat completions endpoint")
        return self


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    service = ApplicationService(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        service.start()
        try:
            yield
        finally:
            service.stop()

    app = FastAPI(title="Autosubtitle", version="0.2.0", lifespan=lifespan)
    app.state.service = service
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def get_status() -> dict[str, object]:
        return service.status()

    @app.get("/api/jobs")
    def get_jobs(limit: int = 100) -> list[dict[str, object]]:
        return [job.to_dict() for job in service.store.list_jobs(min(max(limit, 1), 500))]

    @app.get("/api/jobs/{job_id}/download")
    def download_subtitle(job_id: int) -> FileResponse:
        job = service.store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Subtitle is not ready")
        try:
            output_path = resolved_settings.validate_path(Path(job.output_path))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            output_path,
            media_type="application/x-subrip",
            filename=output_path.name,
        )

    @app.get("/api/settings")
    def get_global_settings() -> dict[str, object]:
        values = service.store.get_settings()
        api_key = values.pop("llm_api_key", None)
        values["llm_api_key_configured"] = bool(api_key)
        return values

    @app.put("/api/settings")
    def update_global_settings(request: GlobalSettingsRequest) -> dict[str, object]:
        current = service.store.get_settings()
        values = request.model_dump()
        if values["llm_api_key"] is None:
            values["llm_api_key"] = current.get("llm_api_key")
        updated = service.store.update_settings(values)
        api_key = updated.pop("llm_api_key", None)
        updated["llm_api_key_configured"] = bool(api_key)
        return updated

    @app.post("/api/jobs/path", status_code=status.HTTP_201_CREATED)
    def enqueue_path(request: PathJobRequest) -> dict[str, object]:
        try:
            path = resolved_settings.validate_path(Path(request.path))
            if not is_supported_video(path):
                raise ValueError(f"Unsupported video extension: {path.suffix}")
            job, created = service.store.enqueue(path, source="manual")
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job": job.to_dict(), "created": created}

    @app.post("/api/jobs/upload", status_code=status.HTTP_201_CREATED)
    def upload_video(file: Annotated[UploadFile, File(...)]) -> dict[str, object]:
        filename = Path(file.filename or "video").name
        if not filename or not is_supported_video(Path(filename)):
            raise HTTPException(status_code=400, detail="Unsupported video extension")

        destination = resolved_settings.upload_dir / filename
        if destination.exists():
            destination = destination.with_name(
                f"{destination.stem}-{uuid4().hex[:8]}{destination.suffix}"
            )
        temporary = destination.with_name(f".{destination.name}.part")
        try:
            with temporary.open("xb") as output:
                shutil.copyfileobj(file.file, output, length=1024 * 1024)
            os.replace(temporary, destination)
            job, _ = service.store.enqueue(destination, source="upload")
        except ValueError as exc:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
        finally:
            file.file.close()
        return {"job": job.to_dict(), "created": True}

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: int) -> dict[str, bool]:
        if not service.store.retry_job(job_id):
            raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
        return {"queued": True}

    @app.get("/api/watch-folders")
    def get_watch_folders() -> list[dict[str, object]]:
        return [folder.to_dict() for folder in service.store.list_watch_folders()]

    @app.post("/api/watch-folders", status_code=status.HTTP_201_CREATED)
    def add_watch_folder(request: WatchFolderRequest) -> dict[str, object]:
        try:
            path = resolved_settings.validate_path(
                Path(request.path), require_directory=True
            )
            folder = service.store.add_watch_folder(path, request.recursive)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return folder.to_dict()

    @app.delete("/api/watch-folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_watch_folder(folder_id: int) -> None:
        if not service.store.remove_watch_folder(folder_id):
            raise HTTPException(status_code=404, detail="Watch folder not found")

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Autosubtitle web service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
