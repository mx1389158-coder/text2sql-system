from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from apps.api.app.dependencies import get_orchestrator

from .runner import EvaluationRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible Text2SQL evaluation")
    parser.add_argument("dataset")
    parser.add_argument("--strategy", choices=["baseline", "optimized"], default="optimized")
    parser.add_argument("--output", default="experiments/reports/latest.json")
    args = parser.parse_args()
    runner = EvaluationRunner(get_orchestrator())
    summary = asyncio.run(runner.run(args.dataset, strategy=args.strategy))
    runner.write(summary, args.output)
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

