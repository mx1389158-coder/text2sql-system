from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from apps.api.app.dependencies import get_orchestrator
from packages.evaluation.acceptance import build_acceptance_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safety and clarification acceptance checks")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/reports/safety-ambiguity-v1.json"),
    )
    parser.add_argument(
        "--skip-resolution",
        action="store_true",
        help="Only run deterministic safety and 80-case clarification detection checks",
    )
    args = parser.parse_args()
    report = asyncio.run(
        build_acceptance_report(
            get_orchestrator(),
            safety_path="data/evaluation/safety_v1.jsonl",
            request_safety_path="data/evaluation/request_safety_v1.jsonl",
            ambiguity_path="data/evaluation/ambiguity_v1.jsonl",
            resolution_path="data/evaluation/clarification_resolution_v1.jsonl",
            run_resolution=not args.skip_resolution,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "safety": report["safety"]["combined"],
        "clarification_detection": report["clarification"]["detection"],
        "clarification_resolution": report["clarification"]["resolution"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
