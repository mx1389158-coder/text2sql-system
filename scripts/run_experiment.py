from __future__ import annotations

import argparse
import asyncio
import json

from apps.api.app.dependencies import get_orchestrator
from packages.evaluation.experiments import run_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one frozen, reproducible experiment manifest")
    parser.add_argument("manifest")
    parser.add_argument("--output-dir", default="experiments/reports")
    args = parser.parse_args()
    report = asyncio.run(run_manifest(get_orchestrator(), args.manifest, args.output_dir))
    summary = {
        key: value
        for key, value in report["summary"].items()
        if key not in {"failures", "samples"}
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
