from __future__ import annotations

import hashlib
import json
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Generic, Optional, Tuple, TypeVar

from ..schemas.query import Intent, QueryRecord, QueryResult, QueryStatus, SchemaEvidenceResponse


T = TypeVar("T")


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split()).casefold()


def stable_cache_key(namespace: str, **values: object) -> str:
    payload = {"namespace": namespace, **values}
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._values: Dict[str, Tuple[float, T]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[T]:
        if self.ttl_seconds <= 0:
            return None
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.time():
                self._values.pop(key, None)
                return None
            return deepcopy(value)

    def set(self, key: str, value: T) -> None:
        if self.ttl_seconds <= 0:
            return
        with self._lock:
            self._values[key] = (time.time() + self.ttl_seconds, deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


@dataclass
class CachedQueryResult:
    """Reusable inference output without request/session/trace/usage metadata."""

    intent: Intent
    status: QueryStatus
    schema_evidence: Optional[SchemaEvidenceResponse]
    sql: Optional[str]
    result: Optional[QueryResult]
    explanation: Optional[str]
    assumptions: list[str]

    @classmethod
    def from_record(cls, record: QueryRecord) -> "CachedQueryResult":
        result = None
        if record.result is not None:
            result = record.result.model_copy(
                deep=True,
                update={"elapsed_ms": 0.0},
            )
        return cls(
            intent=record.intent,
            status=record.status,
            schema_evidence=(
                record.schema_evidence.model_copy(deep=True)
                if record.schema_evidence is not None
                else None
            ),
            sql=record.sql,
            result=result,
            explanation=record.explanation,
            assumptions=list(record.assumptions),
        )

    def apply_to(self, record: QueryRecord) -> None:
        record.intent = self.intent
        record.status = self.status
        record.schema_evidence = deepcopy(self.schema_evidence)
        record.sql = self.sql
        record.result = deepcopy(self.result)
        record.explanation = self.explanation
        record.assumptions = list(self.assumptions)


class QueryCache(TTLCache[CachedQueryResult]):

    @staticmethod
    def key(
        *,
        question: str,
        clarification: str,
        schema_version: str,
        scope: str,
        policy_version: str,
        strategy: str,
        model_id: str,
        prompt_version: str,
        few_shot_version: str,
        semantic_version: str,
        runtime_version: str,
    ) -> str:
        return stable_cache_key(
            "query-result-v2",
            normalized_question=normalize_question(question),
            normalized_clarification=normalize_question(clarification),
            schema_version=schema_version,
            scope=scope,
            policy_version=policy_version,
            strategy=strategy,
            model_id=model_id,
            prompt_version=prompt_version,
            few_shot_version=few_shot_version,
            semantic_version=semantic_version,
            runtime_version=runtime_version,
        )


