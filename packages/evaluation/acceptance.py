from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from apps.api.app.schemas.query import Intent, QueryStatus
from apps.api.app.services.intent import IntentClassifier
from apps.api.app.services.orchestrator import Text2SQLOrchestrator
from packages.execution.guard import SQLSafetyError

from .metrics import result_value_hash


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rates(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(items)
    attacks = [row for row in rows if not row["should_allow"]]
    normal = [row for row in rows if row["should_allow"]]
    blocked_attacks = sum(not row["allowed"] for row in attacks)
    blocked_normal = sum(not row["allowed"] for row in normal)
    correct = sum(row["allowed"] == row["should_allow"] for row in rows)
    return {
        "total": len(rows),
        "normal": len(normal),
        "attacks": len(attacks),
        "correct": correct,
        "accuracy": correct / max(1, len(rows)),
        "true_positive_rate": blocked_attacks / max(1, len(attacks)),
        "false_positive_rate": blocked_normal / max(1, len(normal)),
        "failures": [row["id"] for row in rows if row["allowed"] != row["should_allow"]],
    }


def evaluate_safety_layers(
    orchestrator: Text2SQLOrchestrator,
    sql_rows: list[dict[str, Any]],
    request_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sql_results = []
    for row in sql_rows:
        try:
            orchestrator.guard.validate_and_rewrite(str(row["sql"]))
            allowed = True
        except SQLSafetyError:
            allowed = False
        sql_results.append({**row, "allowed": allowed})

    classifier = IntentClassifier()
    request_results = []
    for row in request_rows:
        decision = classifier.classify(str(row["question"]))
        request_results.append(
            {
                **row,
                "allowed": decision.intent != Intent.REJECT,
                "decision": decision.intent.value,
            }
        )

    combined = [*sql_results, *request_results]
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in combined:
        category_rows[str(row.get("category", "uncategorized"))].append(row)
    return {
        "combined": _rates(combined),
        "sql_guard": _rates(sql_results),
        "request_intent": _rates(request_results),
        "by_category": {
            category: _rates(rows) for category, rows in sorted(category_rows.items())
        },
    }


async def evaluate_clarification(
    orchestrator: Text2SQLOrchestrator,
    ambiguity_rows: list[dict[str, Any]],
    resolution_rows: list[dict[str, Any]],
    *,
    run_resolution: bool,
) -> dict[str, Any]:
    detections = []
    category_totals: dict[str, list[bool]] = defaultdict(list)
    for row in ambiguity_rows:
        detected = orchestrator.semantic_catalog.ambiguity(str(row["question"]))
        expected_key = str(row["clarification"])
        actual_key = str(detected.get("key")) if detected else None
        correct = actual_key == expected_key
        detections.append(
            {
                "id": row["id"],
                "expected_key": expected_key,
                "actual_key": actual_key,
                "correct": correct,
            }
        )
        category_totals[expected_key].append(correct)

    report: dict[str, Any] = {
        "detection": {
            "total": len(detections),
            "correct": sum(row["correct"] for row in detections),
            "accuracy": sum(row["correct"] for row in detections) / max(1, len(detections)),
            "failures": [row for row in detections if not row["correct"]],
            "by_key": {
                key: {
                    "total": len(values),
                    "correct": sum(values),
                    "accuracy": sum(values) / max(1, len(values)),
                }
                for key, values in sorted(category_totals.items())
            },
        },
        "resolution": {
            "status": "not_run" if not run_resolution else "running",
            "total": len(resolution_rows),
        },
    }
    if not run_resolution:
        return report

    samples = []
    for row in resolution_rows:
        before = await orchestrator.submit(
            str(row["question"]), strategy="optimized", scope="evaluation"
        )
        after = await orchestrator.submit(
            str(row["question"]),
            strategy="optimized",
            scope="evaluation",
            clarification_answer=str(row["clarification_answer"]),
        )
        value_hash = result_value_hash(after.result.rows) if after.result else None
        samples.append(
            {
                "id": row["id"],
                "expected_key": row["clarification"],
                "before_status": before.status.value,
                "before_key": before.clarification.key if before.clarification else None,
                "after_status": after.status.value,
                "predicted_sql": after.sql,
                "expected_value_hash": row.get("expected_value_hash"),
                "actual_value_hash": value_hash,
                "execution_correct": bool(value_hash)
                and value_hash == row.get("expected_value_hash"),
                "model_calls": after.model_calls,
                "repair_rounds": after.repair_rounds,
                "error": after.error_message,
            }
        )
    report["resolution"] = {
        "status": "completed",
        "total": len(samples),
        "before_clarification_accuracy": sum(
            row["before_status"] == QueryStatus.CLARIFICATION_REQUIRED.value
            and row["before_key"] == row["expected_key"]
            for row in samples
        )
        / max(1, len(samples)),
        "after_execution_success_rate": sum(
            row["after_status"] == QueryStatus.COMPLETED.value for row in samples
        )
        / max(1, len(samples)),
        "after_execution_accuracy": sum(row["execution_correct"] for row in samples)
        / max(1, len(samples)),
        "samples": samples,
    }
    return report


async def build_acceptance_report(
    orchestrator: Text2SQLOrchestrator,
    *,
    safety_path: str | Path,
    request_safety_path: str | Path,
    ambiguity_path: str | Path,
    resolution_path: str | Path,
    run_resolution: bool,
) -> dict[str, Any]:
    def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    sql_rows = read_jsonl(safety_path)
    request_rows = read_jsonl(request_safety_path)
    ambiguity_rows = read_jsonl(ambiguity_path)
    resolution_rows = read_jsonl(resolution_path)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": {
            "sql_safety": {"path": str(safety_path), "sha256": _sha256(safety_path)},
            "request_safety": {
                "path": str(request_safety_path),
                "sha256": _sha256(request_safety_path),
            },
            "ambiguity": {"path": str(ambiguity_path), "sha256": _sha256(ambiguity_path)},
            "clarification_resolution": {
                "path": str(resolution_path),
                "sha256": _sha256(resolution_path),
            },
        },
        "safety": evaluate_safety_layers(orchestrator, sql_rows, request_rows),
        "clarification": await evaluate_clarification(
            orchestrator,
            ambiguity_rows,
            resolution_rows,
            run_resolution=run_resolution,
        ),
    }
