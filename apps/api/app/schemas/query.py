from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


LEGACY_UNSCOPED = "__legacy_unscoped__"


class QueryStatus(str, Enum):
    RUNNING = "running"
    CLARIFICATION_REQUIRED = "clarification_required"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class Intent(str, Enum):
    QUERY = "QUERY"
    META = "META"
    CLARIFY = "CLARIFY"
    REJECT = "REJECT"


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None
    strategy: str = "optimized"


class ClarifyRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


class Clarification(BaseModel):
    key: str
    question: str
    options: List[str] = []


class SchemaEvidenceResponse(BaseModel):
    selected_tables: List[str] = []
    join_path_tables: List[str] = []
    table_scores: Dict[str, float] = {}
    mschema: str = ""
    estimated_tokens: int = 0
    semantic_definitions: List[str] = []
    selected_columns: List[str] = []
    confidence: float = 0.0
    expanded: bool = False


class QueryResult(BaseModel):
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    truncated: bool = False
    elapsed_ms: float = 0.0


class TraceEvent(BaseModel):
    stage: str
    status: str
    elapsed_ms: float = 0.0
    detail: Dict[str, Any] = {}
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QueryRecord(BaseModel):
    query_id: str
    trace_id: str
    # Records created before scope persistence are deliberately isolated.  They
    # are not silently assigned to the default scope during deserialization.
    scope: str = Field(default=LEGACY_UNSCOPED, min_length=1, max_length=128)
    session_id: Optional[str] = None
    question: str
    clarification_answer: Optional[str] = None
    intent: Intent = Intent.QUERY
    status: QueryStatus = QueryStatus.RUNNING
    clarification: Optional[Clarification] = None
    schema_evidence: Optional[SchemaEvidenceResponse] = None
    sql: Optional[str] = None
    result: Optional[QueryResult] = None
    explanation: Optional[str] = None
    assumptions: List[str] = []
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    repair_rounds: int = 0
    repair_succeeded: bool = False
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    strategy: str = "optimized"
    cached: bool = False
    trace: List[TraceEvent] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackRequest(BaseModel):
    query_id: str
    rating: Literal["correct", "incorrect"]
    category: Optional[str] = None
    corrected_sql: Optional[str] = None
    comment: Optional[str] = Field(default=None, max_length=2000)


class EvalRunRequest(BaseModel):
    dataset_path: str = "data/processed/smoke.jsonl"
    model: str = "demo"
    strategy: str = "optimized"
    experiment_id: Optional[str] = None

