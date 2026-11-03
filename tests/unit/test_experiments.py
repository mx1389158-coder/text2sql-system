from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from apps.api.app.schemas.query import QueryRecord, QueryStatus
from packages.evaluation.experiments import run_manifest
from packages.evaluation.runner import EvaluationRunner


def test_manifest_rejects_mismatched_model_token_budget(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "experiment.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "id": "budget-mismatch",
                "dataset": str(dataset),
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "model_max_tokens": 192,
            }
        ),
        encoding="utf-8",
    )
    orchestrator = SimpleNamespace(
        settings=SimpleNamespace(model_max_tokens=256),
        generator=SimpleNamespace(provider=SimpleNamespace(max_tokens=256)),
    )

    with pytest.raises(ValueError, match="configured provider budget"):
        asyncio.run(run_manifest(orchestrator, manifest, tmp_path / "reports"))


def test_manifest_reuses_matching_completed_report(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":"one","question":"test"}\n', encoding="utf-8")
    manifest_payload = {
        "id": "resume-complete",
        "dataset": str(dataset),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "model_max_tokens": 192,
        "strategy": "baseline",
    }
    manifest = tmp_path / "experiment.yaml"
    manifest.write_text(yaml.safe_dump(manifest_payload), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    completed = {
        "experiment": manifest_payload,
        "dataset_sha256": manifest_payload["dataset_sha256"],
        "runtime": {
            "configured_model": "base",
            "provider": "openai-compatible",
            "model_max_tokens": 192,
            "model_parse_retries": 1,
            "evaluation_concurrency": 1,
        },
        "summary": {"total": 1, "execution_accuracy": 1.0},
    }
    (reports / "resume-complete.json").write_text(
        json.dumps(completed), encoding="utf-8"
    )
    orchestrator = SimpleNamespace(
        settings=SimpleNamespace(
            model_max_tokens=192,
            llm_model="base",
            llm_provider="openai-compatible",
            model_parse_retries=1,
            evaluation_concurrency=1,
        ),
        generator=SimpleNamespace(provider=SimpleNamespace(max_tokens=192)),
    )

    report = asyncio.run(run_manifest(orchestrator, manifest, reports))

    assert report["summary"]["execution_accuracy"] == 1.0
    assert report["resume"]["reused_completed_report"] is True


def test_runner_resumes_completed_sample_from_checkpoint(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "clarify-one",
                "question": "ambiguous",
                "clarification": {"key": "metric"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = QueryRecord(
        query_id="query-one",
        trace_id="trace-one",
        question="ambiguous",
        status=QueryStatus.CLARIFICATION_REQUIRED,
    )
    context = {"experiment_id": "checkpoint-test"}
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "version": 1,
                "context": context,
                "wall_time_ms": 123.0,
                "peak_vram_mb": None,
                "completed": {
                    "clarify-one": {
                        "record": record.model_dump(mode="json"),
                        "latency_ms": 12.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class ResumeOnlyOrchestrator:
        settings = SimpleNamespace(evaluation_concurrency=1)
        guard = SimpleNamespace()

        async def submit(self, *_args, **_kwargs):
            raise AssertionError("completed checkpoint sample must not be submitted again")

    summary = asyncio.run(
        EvaluationRunner(ResumeOnlyOrchestrator()).run(
            dataset,
            checkpoint_path=checkpoint,
            checkpoint_context=context,
        )
    )

    assert summary.total == 1
    assert summary.clarification_accuracy == 1.0
    assert summary.wall_time_ms >= 123.0
