from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the strict equal-budget final 2x2")
    parser.add_argument(
        "--matrix", type=Path, default=Path("experiments/canonical_2x2.json")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/experiments/canonical_2x2_validation.json"),
    )
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    validated = {}
    failures = []
    for planned_id, cell in matrix["cells"].items():
        actual_id = cell["actual_run"]
        report_path = Path("experiments/reports") / f"{actual_id}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        experiment = report["experiment"]
        summary = report["summary"]
        checks = {
            "dataset_sha256": report["dataset_sha256"] == matrix["dataset_sha256"],
            "model_max_tokens": experiment.get("model_max_tokens")
            == matrix["model_max_tokens"],
            "max_model_calls_per_sample": experiment.get("max_model_calls_per_sample")
            == matrix["max_model_calls_per_sample"],
            "model": experiment.get("model") == cell["model"],
            "strategy": experiment.get("strategy") == cell["strategy"],
        }
        if not all(checks.values()):
            failures.append({"planned_id": planned_id, "checks": checks})
        validated[planned_id] = {
            "actual_run": actual_id,
            "checks": checks,
            "sql_valid_rate": summary["sql_valid_rate"],
            "execution_accuracy": summary["execution_accuracy"],
            "p50_latency_ms": summary["p50_latency_ms"],
            "p95_latency_ms": summary["p95_latency_ms"],
            "model_calls": summary["model_calls"],
            "prompt_tokens": summary["prompt_tokens"],
            "completion_tokens": summary["completion_tokens"],
        }
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not failures else "failed",
        "matrix": str(args.matrix),
        "historical_ids_preserved": True,
        "failures": failures,
        "cells": validated,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
