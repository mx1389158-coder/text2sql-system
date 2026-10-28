from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Sequence


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def normalize_rows(
    columns: Sequence[str], rows: Iterable[Sequence[Any]], order_sensitive: bool = True
) -> List[Dict[str, Any]]:
    normalized = [
        {str(column): json_safe(value) for column, value in zip(columns, row, strict=False)}
        for row in rows
    ]
    if not order_sensitive:
        normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return normalized


def result_hash(columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    payload = normalize_rows(columns, rows, order_sensitive=False)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

