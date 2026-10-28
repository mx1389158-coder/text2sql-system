from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    mschema: str
    semantic_definitions: List[str] = field(default_factory=list)
    few_shots: List[str] = field(default_factory=list)
    clarification: Optional[str] = None
    error_feedback: Optional[str] = None


@dataclass(frozen=True)
class GeneratedCandidate:
    sql: str
    intent: str = "QUERY"
    used_tables: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    raw_response: str = ""
    temperature: float = 0.0
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider_calls: int = 1


@dataclass(frozen=True)
class CandidateScore:
    candidate: GeneratedCandidate
    static_valid: bool
    schema_coverage: float
    executed: bool = False
    non_empty: bool = False
    execution_ms: float = 0.0
    error: Optional[str] = None
    semantic_score: float = 0.0

