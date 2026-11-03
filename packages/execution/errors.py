from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCategory(str, Enum):
    SYNTAX = "syntax_error"
    UNKNOWN_RELATION = "unknown_relation"
    UNKNOWN_COLUMN = "unknown_column"
    TYPE_MISMATCH = "type_mismatch"
    TIMEOUT = "timeout"
    PERMISSION = "permission_denied"
    SAFETY = "safety_rejected"
    EMPTY = "empty_result"
    CONNECTION = "connection_error"
    UNKNOWN = "unknown_error"


@dataclass(frozen=True)
class ClassifiedError:
    category: ErrorCategory
    safe_message: str
    repairable: bool
    sqlstate: Optional[str] = None


def classify_database_error(error: Exception) -> ClassifiedError:
    sqlstate = getattr(error, "sqlstate", None)
    message = str(error)
    lowered = message.lower()
    if sqlstate == "42601" or "syntax" in lowered:
        category = ErrorCategory.SYNTAX
    elif sqlstate == "42P01" or "no such table" in lowered or "relation" in lowered and "exist" in lowered:
        category = ErrorCategory.UNKNOWN_RELATION
    elif sqlstate == "42703" or "no such column" in lowered or "column" in lowered and "exist" in lowered:
        category = ErrorCategory.UNKNOWN_COLUMN
    elif sqlstate in {"42804", "42883"} or "type" in lowered and "mismatch" in lowered:
        category = ErrorCategory.TYPE_MISMATCH
    # Connection failures may themselves contain the word "timeout". They are
    # infrastructure errors, not SQL defects, and must not consume a model
    # repair round.
    elif (
        "connect" in lowered
        or "connection" in lowered
        or sqlstate is not None
        and str(sqlstate).startswith("08")
    ):
        category = ErrorCategory.CONNECTION
    elif sqlstate in {"57014", "55P03"} or "timeout" in lowered or "interrupted" in lowered:
        category = ErrorCategory.TIMEOUT
    elif sqlstate == "42501" or "permission" in lowered or "read-only" in lowered:
        category = ErrorCategory.PERMISSION
    else:
        category = ErrorCategory.UNKNOWN
    safe = re.sub(r"(password|token|secret)\s*[=:]\s*\S+", r"\1=[REDACTED]", message, flags=re.I)
    safe = safe.replace("\n", " ")[:500]
    return ClassifiedError(
        category=category,
        safe_message=safe,
        repairable=category
        in {
            ErrorCategory.SYNTAX,
            ErrorCategory.UNKNOWN_RELATION,
            ErrorCategory.UNKNOWN_COLUMN,
            ErrorCategory.TYPE_MISMATCH,
            ErrorCategory.TIMEOUT,
        },
        sqlstate=sqlstate,
    )

