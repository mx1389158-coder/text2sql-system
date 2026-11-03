from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach a rigorous multi-snapshot Test-Suite result to an experiment report"
    )
    parser.add_argument("experiment", type=Path)
    parser.add_argument("test_suite", type=Path)
    args = parser.parse_args()
    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    suite = json.loads(args.test_suite.read_text(encoding="utf-8"))
    if suite["source_experiment"] != experiment["experiment"]["id"]:
        raise ValueError("test-suite source experiment does not match target report")
    summary = experiment["summary"]
    summary["fixed_snapshot_accuracy"] = summary["execution_accuracy"]
    summary["test_suite_accuracy"] = suite["summary"]["test_suite_accuracy"]
    summary["test_suite_protocol"] = "three_transactional_postgresql_snapshots"
    experiment["test_suite_report"] = str(args.test_suite).replace("\\", "/")
    args.experiment.write_text(
        json.dumps(experiment, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "experiment": experiment["experiment"]["id"],
                "fixed_snapshot_accuracy": summary["fixed_snapshot_accuracy"],
                "test_suite_accuracy": summary["test_suite_accuracy"],
                "protocol": summary["test_suite_protocol"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
