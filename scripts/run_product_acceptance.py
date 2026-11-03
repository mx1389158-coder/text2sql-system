from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the four product acceptance scenarios")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/product_acceptance_v2.jsonl"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/qa/product_acceptance_v2.json")
    )
    args = parser.parse_args()

    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    client = TestClient(app)
    results = []
    for case in cases:
        response = client.post(
            "/api/v1/query",
            json={"question": case["question"], "strategy": "optimized"},
        )
        response.raise_for_status()
        payload = response.json()
        initial_status = payload["status"]
        status_ok = initial_status == case["expected_status"]
        resumed_status = None
        if case.get("clarification_answer") and initial_status == "clarification_required":
            resumed = client.post(
                f"/api/v1/query/{payload['query_id']}/clarify",
                json={"answer": case["clarification_answer"]},
            )
            resumed.raise_for_status()
            resumed_status = resumed.json()["status"]
            status_ok = status_ok and resumed_status == "completed"
        selected_tables = set((payload.get("schema_evidence") or {}).get("selected_tables", []))
        expected_tables = set(case.get("expected_tables", []))
        tables_ok = not expected_tables or expected_tables <= selected_tables
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "initial_status": initial_status,
                "resumed_status": resumed_status,
                "status_ok": status_ok,
                "tables_ok": tables_ok,
                "passed": status_ok and tables_ok,
            }
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(item["passed"] for item in results) else "failed",
        "total": len(results),
        "passed": sum(item["passed"] for item in results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
