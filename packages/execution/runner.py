from __future__ import annotations

import sqlite3
import time
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import sqlglot

from .errors import ClassifiedError, classify_database_error
from .normalizer import normalize_rows


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    truncated: bool = False
    error: Optional[ClassifiedError] = None


class DatabaseRunner(ABC):
    @abstractmethod
    def execute(self, sql: str) -> ExecutionResult:
        raise NotImplementedError


class PostgresRunner(DatabaseRunner):
    def __init__(
        self,
        database_url: str,
        max_rows: int = 200,
        statement_timeout_ms: int = 5000,
        lock_timeout_ms: int = 1000,
    ):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://")
        self.max_rows = max_rows
        self.statement_timeout_ms = statement_timeout_ms
        self.lock_timeout_ms = lock_timeout_ms

    def execute(self, sql: str) -> ExecutionResult:
        import psycopg

        started = time.perf_counter()
        try:
            with psycopg.connect(self.database_url, autocommit=False) as connection:
                with connection.transaction():
                    connection.execute("SET TRANSACTION READ ONLY")
                    connection.execute(f"SET LOCAL statement_timeout = '{int(self.statement_timeout_ms)}ms'")
                    connection.execute(f"SET LOCAL lock_timeout = '{int(self.lock_timeout_ms)}ms'")
                    cursor = connection.execute(sql)
                    columns = [item.name for item in cursor.description or []]
                    raw_rows = cursor.fetchmany(self.max_rows + 1)
                    truncated = len(raw_rows) > self.max_rows
                    raw_rows = raw_rows[: self.max_rows]
                    rows = normalize_rows(columns, raw_rows)
            return ExecutionResult(
                ok=True,
                columns=columns,
                rows=rows,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                truncated=truncated,
            )
        except Exception as error:
            return ExecutionResult(
                ok=False,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=classify_database_error(error),
            )


class SQLiteRunner(DatabaseRunner):
    """Read-only local demo runner. PostgreSQL remains the production target."""

    def __init__(self, path: str | Path, max_rows: int = 200, timeout_ms: int = 5000):
        self.path = str(Path(path).resolve())
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms

    def execute(self, sql: str) -> ExecutionResult:
        started = time.perf_counter()
        deadline = started + self.timeout_ms / 1000
        connection: Optional[sqlite3.Connection] = None
        try:
            portable_sql = re.sub(
                r"([a-zA-Z_][\w.]*?)\s*\+\s*INTERVAL\s*'(\d+)\s+days?'",
                r"DATETIME(\1, '+\2 days')",
                sql,
                flags=re.IGNORECASE,
            )
            portable_sql = re.sub(
                r"EXTRACT\s*\(\s*EPOCH\s+FROM\s*\(\s*([\w.]+)\s*-\s*([\w.]+)\s*\)\s*\)",
                r"((JULIANDAY(\1) - JULIANDAY(\2)) * 86400.0)",
                portable_sql,
                flags=re.IGNORECASE,
            )
            translated = sqlglot.transpile(portable_sql, read="postgres", write="sqlite")[0]
            connection = sqlite3.connect(self.path, timeout=1)
            connection.execute("PRAGMA query_only = ON")
            connection.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 2000)
            cursor = connection.execute(translated)
            columns = [item[0] for item in cursor.description or []]
            raw_rows = cursor.fetchmany(self.max_rows + 1)
            truncated = len(raw_rows) > self.max_rows
            rows = normalize_rows(columns, raw_rows[: self.max_rows])
            return ExecutionResult(
                ok=True,
                columns=columns,
                rows=rows,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                truncated=truncated,
            )
        except Exception as error:
            return ExecutionResult(
                ok=False,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=classify_database_error(error),
            )
        finally:
            if connection is not None:
                connection.close()

