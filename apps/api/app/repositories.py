from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .schemas.query import FeedbackRequest, QueryRecord


class QueryRepository:
    def __init__(self, database_path: str | Path | None = None):
        self._records: Dict[str, QueryRecord] = {}
        self._lock = threading.RLock()
        self.database_path = Path(database_path) if database_path else None
        if self.database_path:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.database_path is None:
            raise RuntimeError("repository is in-memory")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS query_records (
                    query_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    def save(self, record: QueryRecord) -> QueryRecord:
        with self._lock:
            record.updated_at = datetime.now(timezone.utc)
            self._records[record.query_id] = record
            if self.database_path:
                with self._connect() as connection:
                    connection.execute(
                        """INSERT INTO query_records(query_id, payload, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(query_id) DO UPDATE SET
                          payload=excluded.payload, updated_at=excluded.updated_at""",
                        (record.query_id, record.model_dump_json(), record.updated_at.isoformat()),
                    )
            return record

    def get(self, query_id: str) -> Optional[QueryRecord]:
        with self._lock:
            record = self._records.get(query_id)
            if record is not None or not self.database_path:
                return record
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload FROM query_records WHERE query_id = ?", (query_id,)
                ).fetchone()
            if row is None:
                return None
            record = QueryRecord.model_validate_json(row["payload"])
            self._records[query_id] = record
            return record

    def list(self, limit: int = 100) -> List[QueryRecord]:
        with self._lock:
            if not self.database_path:
                return sorted(
                    self._records.values(), key=lambda item: item.updated_at, reverse=True
                )[:limit]
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT payload FROM query_records ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [QueryRecord.model_validate_json(row["payload"]) for row in rows]


class FeedbackRepository:
    def __init__(self, path: str | Path = "data/interim/badcases.jsonl"):
        self.path = Path(path)
        self._lock = threading.RLock()

    def append(self, feedback: FeedbackRequest, query: QueryRecord) -> None:
        payload = {
            "query_id": feedback.query_id,
            "rating": feedback.rating,
            "category": feedback.category,
            "corrected_sql": feedback.corrected_sql,
            "comment": feedback.comment,
            "question": query.question,
            "predicted_sql": query.sql,
            "trace_id": query.trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "training_status": "candidate_only",
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list(self, limit: int = 200) -> List[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            with self.path.open("r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        return list(reversed(rows[-limit:]))


class JobRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS evaluation_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, job_id: str, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO evaluation_jobs
                (job_id, status, payload, created_at, updated_at)
                VALUES (?, 'queued', ?, ?, ?)""",
                (job_id, json.dumps(payload, ensure_ascii=False), now, now),
            )
        return self.get(job_id) or {}

    def update(
        self, job_id: str, status: str, result: Optional[dict] = None, error: Optional[str] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE evaluation_jobs
                SET status = ?, result = ?, error = ?, updated_at = ? WHERE job_id = ?""",
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error,
                    now,
                    job_id,
                ),
            )

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._decode(row) if row else None

    def list(self, limit: int = 100) -> List[dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evaluation_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode(row) for row in rows]

    def recoverable(self) -> List[dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evaluation_jobs WHERE status IN ('queued', 'running')"
            ).fetchall()
        return [self._decode(row) for row in rows]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "payload": json.loads(row["payload"]),
            "summary": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

