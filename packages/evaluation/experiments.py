from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import yaml

from apps.api.app.services.orchestrator import Text2SQLOrchestrator

from .runner import EvaluationRunner


ALLOWED_OVERRIDES = {
    "candidate_count",
    "candidate_semantic_threshold",
    "max_repair_rounds",
    "schema_top_k",
    "schema_token_budget",
    "enable_few_shots",
    "enable_fk_completion",
    "enable_adaptive_schema",
    "few_shot_count",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


async def run_manifest(
    orchestrator: Text2SQLOrchestrator,
    manifest_path: str | Path,
    output_dir: str | Path = "experiments/reports",
    *,
    resume: bool = True,
) -> Dict[str, Any]:
    path = Path(manifest_path)
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("id"):
        raise ValueError("experiment manifest requires id")
    dataset = Path(manifest["dataset"])
    if not dataset.exists():
        raise FileNotFoundError(dataset)
    actual_hash = sha256(dataset)
    expected_hash = manifest.get("dataset_sha256")
    if expected_hash and expected_hash != actual_hash:
        raise ValueError("frozen dataset hash mismatch")
    declared_token_budget = manifest.get("model_max_tokens")
    if (
        declared_token_budget is not None
        and int(declared_token_budget) != orchestrator.settings.model_max_tokens
    ):
        raise ValueError(
            "manifest model_max_tokens does not match the configured provider budget"
        )
    provider_budget = getattr(orchestrator.generator.provider, "max_tokens", None)
    if declared_token_budget is not None and provider_budget is not None:
        if int(declared_token_budget) != int(provider_budget):
            raise ValueError(
                "manifest model_max_tokens does not match the active provider budget"
            )
    overrides = dict(manifest.get("overrides") or {})
    unknown = set(overrides) - ALLOWED_OVERRIDES
    if unknown:
        raise ValueError(f"unsupported experiment overrides: {sorted(unknown)}")
    output = Path(output_dir) / f"{manifest['id']}.json"
    checkpoint = Path(output_dir).parent / "checkpoints" / f"{manifest['id']}.json"
    checkpoint_context = {
        "experiment_id": str(manifest["id"]),
        "manifest_sha256": sha256(path),
        "dataset_sha256": actual_hash,
        "model": orchestrator.settings.llm_model,
        "provider": orchestrator.settings.llm_provider,
        "model_max_tokens": orchestrator.settings.model_max_tokens,
        "model_parse_retries": orchestrator.settings.model_parse_retries,
        "evaluation_concurrency": orchestrator.settings.evaluation_concurrency,
        "strategy": str(manifest.get("strategy", "optimized")),
    }
    if resume and output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        runtime = existing.get("runtime", {})
        if (
            existing.get("experiment") == manifest
            and existing.get("dataset_sha256") == actual_hash
            and runtime.get("configured_model") == orchestrator.settings.llm_model
            and runtime.get("provider") == orchestrator.settings.llm_provider
            and runtime.get("model_max_tokens") == orchestrator.settings.model_max_tokens
            and runtime.get("model_parse_retries")
            == orchestrator.settings.model_parse_retries
            and runtime.get("evaluation_concurrency")
            == orchestrator.settings.evaluation_concurrency
        ):
            existing["resume"] = {"reused_completed_report": True}
            return existing
    if not resume and checkpoint.exists():
        checkpoint.unlink()
    original = {key: getattr(orchestrator.settings, key) for key in overrides}
    few_shot_limit = orchestrator.few_shots.limit
    for key, value in overrides.items():
        setattr(orchestrator.settings, key, value)
    orchestrator.few_shots.limit = orchestrator.settings.few_shot_count
    started = time.perf_counter()
    try:
        summary = await EvaluationRunner(orchestrator).run(
            dataset,
            strategy=str(manifest.get("strategy", "optimized")),
            max_model_calls_per_sample=manifest.get("max_model_calls_per_sample"),
            checkpoint_path=checkpoint,
            checkpoint_context=checkpoint_context,
        )
    finally:
        for key, value in original.items():
            setattr(orchestrator.settings, key, value)
        orchestrator.few_shots.limit = few_shot_limit
    report = {
        "experiment": manifest,
        "dataset_sha256": actual_hash,
        "git_sha": git_sha(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_time_ms": (time.perf_counter() - started) * 1000,
            "configured_model": orchestrator.settings.llm_model,
            "provider": orchestrator.settings.llm_provider,
            "model_max_tokens": orchestrator.settings.model_max_tokens,
            "model_parse_retries": orchestrator.settings.model_parse_retries,
            "evaluation_concurrency": orchestrator.settings.evaluation_concurrency,
        },
        "summary": asdict(summary),
        "resume": {
            "sample_checkpointing": True,
            "reused_completed_report": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint.unlink(missing_ok=True)
    return report
