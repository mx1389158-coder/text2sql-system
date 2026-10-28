from packages.evaluation.safety import SafetyCase, evaluate_safety
import json
from pathlib import Path


def test_security_attack_set(guard):
    cases = [
        SafetyCase("SELECT id FROM orders", True, "normal-select"),
        SafetyCase("WITH x AS (SELECT id FROM orders) SELECT * FROM x", True, "normal-cte"),
        SafetyCase("UPDATE orders SET status='paid'", False, "update"),
        SafetyCase("SELECT * FROM orders; DELETE FROM orders", False, "stacked"),
        SafetyCase("SELECT pg_read_file('/etc/passwd')", False, "file-read"),
        SafetyCase("SELECT * FROM information_schema.tables", False, "catalog"),
    ]
    report = evaluate_safety(guard, cases)
    assert report.correct == report.total
    assert report.true_positive_rate == 1.0
    assert report.false_positive_rate == 0.0


def test_full_security_dataset_has_100_passing_cases(guard):
    path = Path(__file__).resolve().parents[2] / "data/evaluation/safety_v1.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 100
    cases = [SafetyCase(row["sql"], row["should_allow"], row["id"]) for row in rows]
    report = evaluate_safety(guard, cases)
    assert report.correct == report.total, report.failures

