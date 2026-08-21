from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    input_path: str
    output_path: str
    source: str
    status: str
    error: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WatchFolder:
    id: int
    path: str
    recursive: bool
    enabled: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Store:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_path TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(input_path, size, mtime_ns)
                );
                CREATE INDEX IF NOT EXISTS jobs_status_id ON jobs(status, id);
                CREATE TABLE IF NOT EXISTS watch_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    recursive INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "UPDATE jobs SET status = 'queued', error = ? WHERE status = 'processing'",
                ("Service restarted while the job was processing",),
            )

    def seed_settings(self, defaults: dict[str, Any]) -> None:
        timestamp = _now()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO app_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                [
                    (key, json.dumps(value), timestamp)
                    for key, value in defaults.items()
                ],
            )

    def get_settings(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT key, value FROM app_settings ORDER BY key"
            ).fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        timestamp = _now()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                [
                    (key, json.dumps(value), timestamp)
                    for key, value in values.items()
                ],
            )
        return self.get_settings()

    def enqueue(self, input_path: Path, source: str) -> tuple[Job, bool]:
        stat = input_path.stat()
        output_path = input_path.with_suffix(".srt")
        timestamp = _now()
        with self._connect() as connection:
            collision = connection.execute(
                """
                SELECT input_path FROM jobs
                WHERE output_path = ? AND input_path != ?
                  AND status IN ('queued', 'processing', 'completed')
                LIMIT 1
                """,
                (str(output_path), str(input_path)),
            ).fetchone()
            if collision:
                raise ValueError(
                    f"Subtitle output collision with {collision['input_path']}: {output_path}"
                )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    input_path, output_path, source, status, error,
                    size, mtime_ns, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', NULL, ?, ?, ?, ?)
                """,
                (
                    str(input_path),
                    str(output_path),
                    source,
                    stat.st_size,
                    stat.st_mtime_ns,
                    timestamp,
                    timestamp,
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                """
                SELECT id, input_path, output_path, source, status, error,
                       created_at, updated_at
                FROM jobs WHERE input_path = ? AND size = ? AND mtime_ns = ?
                """,
                (str(input_path), stat.st_size, stat.st_mtime_ns),
            ).fetchone()
        return self._row_to_job(row), created

    def claim_next_job(self) -> Job | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status = 'processing', error = NULL, updated_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            job_row = connection.execute(
                """
                SELECT id, input_path, output_path, source, status, error,
                       created_at, updated_at FROM jobs WHERE id = ?
                """,
                (row["id"],),
            ).fetchone()
        return self._row_to_job(job_row)

    def finish_job(self, job_id: int, status: str, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, _now(), job_id),
            )

    def retry_job(self, job_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = 'queued', error = NULL, updated_at = ?
                WHERE id = ? AND status = 'failed'
                """,
                (_now(), job_id),
            )
        return cursor.rowcount == 1

    def list_jobs(self, limit: int = 100) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, input_path, output_path, source, status, error,
                       created_at, updated_at FROM jobs ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: int) -> Job | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, input_path, output_path, source, status, error,
                       created_at, updated_at FROM jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def add_watch_folder(self, path: Path, recursive: bool) -> WatchFolder:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watch_folders(path, recursive, enabled, created_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(path) DO UPDATE SET recursive = excluded.recursive, enabled = 1
                """,
                (str(path), int(recursive), _now()),
            )
            row = connection.execute(
                "SELECT id, path, recursive, enabled, created_at FROM watch_folders WHERE path = ?",
                (str(path),),
            ).fetchone()
        return self._row_to_watch_folder(row)

    def list_watch_folders(self) -> list[WatchFolder]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, path, recursive, enabled, created_at
                FROM watch_folders WHERE enabled = 1 ORDER BY id
                """
            ).fetchall()
        return [self._row_to_watch_folder(row) for row in rows]

    def remove_watch_folder(self, folder_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM watch_folders WHERE id = ?",
                (folder_id,),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(**dict(row))

    @staticmethod
    def _row_to_watch_folder(row: sqlite3.Row) -> WatchFolder:
        values = dict(row)
        values["recursive"] = bool(values["recursive"])
        values["enabled"] = bool(values["enabled"])
        return WatchFolder(**values)
