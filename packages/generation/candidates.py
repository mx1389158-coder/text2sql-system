from __future__ import annotations

from dataclasses import replace
from typing import Iterable, List

from .models import CandidateScore, GeneratedCandidate, GenerationRequest
from .providers import SQLProvider
from packages.schema_linker.vector import HashingTextEncoder


class CandidateGenerator:
    def __init__(self, provider: SQLProvider):
        self.provider = provider

    async def generate(self, request: GenerationRequest, count: int = 1) -> List[GeneratedCandidate]:
        candidates = [await self.provider.generate(request, temperature=0.0)]
        if count > 1:
            candidates.extend(
                await self.provider.generate_many(
                    request,
                    temperature=0.2,
                    count=count - 1,
                )
            )
        return self._deduplicate(candidates)

    @staticmethod
    def _deduplicate(candidates: Iterable[GeneratedCandidate]) -> List[GeneratedCandidate]:
        unique = {}
        for candidate in candidates:
            normalized = " ".join(candidate.sql.lower().split())
            existing = unique.get(normalized)
            if existing is None:
                unique[normalized] = candidate
            else:
                unique[normalized] = replace(
                    existing,
                    provider_calls=existing.provider_calls + candidate.provider_calls,
                    prompt_tokens=existing.prompt_tokens + candidate.prompt_tokens,
                    completion_tokens=existing.completion_tokens + candidate.completion_tokens,
                )
        return list(unique.values())


class CandidateSelector:
    @staticmethod
    def choose(scores: List[CandidateScore]) -> CandidateScore:
        if not scores:
            raise ValueError("没有可选择的 SQL 候选")
        return max(
            scores,
            key=lambda item: (
                item.static_valid,
                item.executed,
                item.non_empty,
                item.schema_coverage,
                item.semantic_score,
                -item.execution_ms,
            ),
        )


class LightweightCandidateScorer:
    def __init__(self):
        self.encoder = HashingTextEncoder()

    def score(self, question: str, candidate: GeneratedCandidate) -> float:
        evidence = " ".join(
            [candidate.sql, *candidate.used_tables, *candidate.assumptions]
        )
        return round(
            max(
                0.0,
                self.encoder.cosine(
                    self.encoder.encode(question), self.encoder.encode(evidence)
                ),
            ),
            4,
        )

