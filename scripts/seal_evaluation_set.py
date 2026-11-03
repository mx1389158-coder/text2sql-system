from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.evaluation.metrics import result_hash, result_value_hash
from packages.execution.runner import PostgresRunner, SQLiteRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute reviewed gold SQL and create a SQL-free frozen evaluation set"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--database-url", default="sqlite:///data/snapshots/demo.db")
    args = parser.parse_args()
    if args.database_url.startswith("sqlite:///"):
        runner = SQLiteRunner(args.database_url[len("sqlite:///") :], max_rows=10000)
    else:
        runner = PostgresRunner(args.database_url, max_rows=10000, statement_timeout_ms=30000)
    sealed = []
    with args.source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("review_status", "approved") != "approved":
                raise ValueError(f"not approved: {row.get('id')}")
            execution = runner.execute(str(row["sql"]))
            if not execution.ok:
                message = execution.error.safe_message if execution.error else "unknown"
                raise ValueError(f"execution failed: {row.get('id')}: {message}")
            public = {key: value for key, value in row.items() if key != "sql"}
            public["expected_result_hash"] = result_hash(
                execution.rows, bool(row.get("order_sensitive", False))
            )
            public["expected_value_hash"] = result_value_hash(
                execution.rows, bool(row.get("order_sensitive", False))
            )
            sealed.append(public)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in sealed:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"output": str(args.output), "count": len(sealed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
