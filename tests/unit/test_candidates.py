from __future__ import annotations

import asyncio

from packages.generation.candidates import CandidateGenerator
from packages.generation.models import GeneratedCandidate, GenerationRequest
from packages.generation.providers import SQLProvider


class RecordingProvider(SQLProvider):
    def __init__(self) -> None:
        self.single_temperatures: list[float] = []
        self.batch_calls: list[tuple[float, int]] = []

    async def generate(
        self, request: GenerationRequest, temperature: float = 0.0
    ) -> GeneratedCandidate:
        self.single_temperatures.append(temperature)
        return GeneratedCandidate(sql="SELECT 1", temperature=temperature)

    async def generate_many(
        self,
        request: GenerationRequest,
        *,
        temperature: float,
        count: int,
    ) -> list[GeneratedCandidate]:
        self.batch_calls.append((temperature, count))
        return [
            GeneratedCandidate(sql=f"SELECT {index + 2}", temperature=temperature)
            for index in range(count)
        ]


def test_three_candidates_use_one_greedy_and_one_sampled_batch() -> None:
    provider = RecordingProvider()
    request = GenerationRequest(question="测试", mschema="# Table: products")

    candidates = asyncio.run(CandidateGenerator(provider).generate(request, count=3))

    assert [item.sql for item in candidates] == ["SELECT 1", "SELECT 2", "SELECT 3"]
    assert provider.single_temperatures == [0.0]
    assert provider.batch_calls == [(0.2, 2)]
