from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, Iterable, List

import sqlglot


def canonical_sql(sql: str, dialect: str = "postgres") -> str:
    return sqlglot.parse_one(sql, read=dialect).sql(dialect=dialect, pretty=False, normalize=True)


def exact_match(predicted: str, expected: str) -> bool:
    try:
        return canonical_sql(predicted) == canonical_sql(expected)
    except Exception:
        return False


def execution_equal(
    predicted_rows: Iterable[Dict[str, Any]],
    expected_rows: Iterable[Dict[str, Any]],
    order_sensitive: bool = False,
) -> bool:
    def encode(rows: Iterable[Dict[str, Any]]) -> List[str]:
        values = [json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows]
        return values if order_sensitive else sorted(values)

    return encode(predicted_rows) == encode(expected_rows)


def schema_recall(predicted_tables: Iterable[str], gold_tables: Iterable[str]) -> float:
    predicted = {item.lower() for item in predicted_tables}
    gold = {item.lower() for item in gold_tables}
    return 1.0 if not gold else len(predicted & gold) / len(gold)


def column_recall(predicted_columns: Iterable[str], gold_columns: Iterable[str]) -> float:
    predicted = {item.lower() for item in predicted_columns}
    gold = {item.lower() for item in gold_columns}
    return 1.0 if not gold else len(predicted & gold) / len(gold)


def result_hash(rows: Iterable[Dict[str, Any]], order_sensitive: bool = False) -> str:
    encoded = [json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows]
    if not order_sensitive:
        encoded.sort()
    payload = "\n".join(encoded).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def result_value_hash(rows: Iterable[Dict[str, Any]], order_sensitive: bool = False) -> str:
    """Hash result values while ignoring presentation-only output aliases."""
    encoded = [
        json.dumps(list(row.values()), ensure_ascii=False, default=str)
        for row in rows
    ]
    if not order_sensitive:
        encoded.sort()
    payload = "\n".join(encoded).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

