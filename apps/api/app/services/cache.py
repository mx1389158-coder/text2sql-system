from __future__ import annotations

import hashlib
import json
import threading
import time
from copy import deepcopy
from typing import Dict, Generic, Optional, Tuple, TypeVar

from ..schemas.query import QueryRecord


T = TypeVar("T")


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


class QueryCache(TTLCache[QueryRecord]):

    @staticmethod
    def key(question: str, scope: str, catalog_version: str, semantic_version: str) -> str:
        payload = json.dumps(
            [question.strip(), scope, catalog_version, semantic_version],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


