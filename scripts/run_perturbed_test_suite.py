from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.api.app.dependencies import get_orchestrator


PERTURBATIONS = {
    "fixed_snapshot": [],
    "status_and_boundary_shift": [
        "UPDATE shipments SET status=CASE WHEN status='delivered' THEN 'shipped' ELSE 'delivered' END WHERE id % 17 = 0",
        "UPDATE shipments SET delivered_at=delivered_at + INTERVAL '1 day' WHERE delivered_at IS NOT NULL AND id % 19 = 0",
        "UPDATE refunds SET status=CASE WHEN status='approved' THEN 'rejected' ELSE 'approved' END WHERE id % 17 = 0",
        "UPDATE refunds SET amount=ROUND(amount * 1.07, 2), created_at=created_at + INTERVAL '1 day' WHERE id % 19 = 0",
        "UPDATE device_upgrades SET status=CASE WHEN status='failed' THEN 'success' ELSE 'failed' END WHERE id % 17 = 0",
        "UPDATE device_upgrades SET upgraded_at=upgraded_at + INTERVAL '1 day' WHERE id % 19 = 0",
    ],
    "foreign_key_reassignment": [
        "UPDATE customer_addresses SET region_id=(SELECT id FROM regions ORDER BY id DESC LIMIT 1) WHERE id % 13 = 0",
        "UPDATE products SET category_id=(SELECT id FROM product_categories ORDER BY id DESC LIMIT 1) WHERE id % 11 = 0",
        "UPDATE customers SET region_id=(SELECT id FROM regions ORDER BY id LIMIT 1) WHERE id % 13 = 0",
    ],
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _encoded_rows(rows: list[tuple[Any, ...]]) -> Counter[str]:
    return Counter(
        json.dumps(list(row), ensure_ascii=False, default=str, separators=(",", ":"))
        for row in rows
    )


def _execute(connection: Any, sql: str, savepoint: str) -> tuple[bool, Counter[str] | None, str | None]:
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        cursor = connection.execute(sql)
        values = _encoded_rows(cursor.fetchall())
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return True, values, None
    except Exception as error:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return False, None, type(error).__name__


def evaluate_report(
    *,
    database_url: str,
    report_path: Path,
    gold_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    import psycopg

    orchestrator = get_orchestrator()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    gold_by_id = {row["id"]: row for row in _read_jsonl(gold_path)}
    predictions = {
        row["id"]: row for row in report["summary"]["samples"] if row.get("id")
    }
    sample_results: dict[str, dict[str, Any]] = {
        sample_id: {"id": sample_id, "snapshots": {}} for sample_id in gold_by_id
    }
    snapshot_summaries = []

    with psycopg.connect(database_url, autocommit=False) as connection:
        for snapshot_name, statements in PERTURBATIONS.items():
            connection.execute("BEGIN")
            connection.execute("SET LOCAL statement_timeout = '30s'")
            for statement in statements:
                connection.execute(statement)
            correct = 0
            for index, (sample_id, gold) in enumerate(gold_by_id.items()):
                predicted = predictions.get(sample_id, {}).get("predicted_sql")
                result = {
                    "correct": False,
                    "predicted_sql_present": bool(predicted),
                    "gold_error": None,
                    "prediction_error": None,
                }
                if predicted:
                    try:
                        guarded_prediction = orchestrator.guard.validate_and_rewrite(
                            str(predicted)
                        ).sql
                        guarded_gold = orchestrator.guard.validate_and_rewrite(
                            str(gold["sql"])
                        ).sql
                        gold_ok, gold_rows, gold_error = _execute(
                            connection, guarded_gold, f"gold_{index}"
                        )
                        prediction_ok, predicted_rows, prediction_error = _execute(
                            connection, guarded_prediction, f"pred_{index}"
                        )
                        result.update(
                            {
                                "correct": bool(gold_ok and prediction_ok)
                                and gold_rows == predicted_rows,
                                "gold_error": gold_error,
                                "prediction_error": prediction_error,
                            }
                        )
                    except Exception as error:
                        result["prediction_error"] = type(error).__name__
                correct += int(result["correct"])
                sample_results[sample_id]["snapshots"][snapshot_name] = result
            snapshot_summaries.append(
                {
                    "snapshot": snapshot_name,
                    "correct": correct,
                    "total": len(gold_by_id),
                    "accuracy": correct / max(1, len(gold_by_id)),
                }
            )
            connection.rollback()

    samples = list(sample_results.values())
    for sample in samples:
        sample["test_suite_correct"] = all(
            result["correct"] for result in sample["snapshots"].values()
        )
    suite_correct = sum(sample["test_suite_correct"] for sample in samples)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_experiment": report["experiment"]["id"],
        "source_report": str(report_path),
        "gold_dataset": str(gold_path),
        "protocol": {
            "type": "transactional_data_perturbation",
            "snapshots": list(PERTURBATIONS),
            "rollback_after_each_snapshot": True,
            "comparison": "order-insensitive result values; output aliases ignored",
        },
        "summary": {
            "total": len(samples),
            "snapshots": len(PERTURBATIONS),
            "correct_on_all_snapshots": suite_correct,
            "test_suite_accuracy": suite_correct / max(1, len(samples)),
            "per_snapshot": snapshot_summaries,
        },
        "samples": samples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate stored predictions on rolled-back PostgreSQL perturbations"
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--gold", type=Path, default=Path("training/datasets/raw/holdout_v2.jsonl"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("experiments/reports") / f"test-suite-{args.report.stem}.json"
    result = evaluate_report(
        database_url=args.database_url,
        report_path=args.report,
        gold_path=args.gold,
        output_path=output,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
