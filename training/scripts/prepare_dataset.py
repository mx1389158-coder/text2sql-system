from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

import sqlglot

from packages.evaluation.metrics import result_hash
from packages.execution.runner import PostgresRunner, SQLiteRunner


INSTRUCTION = """根据给定的 PostgreSQL Schema 和中文问题生成 SQL。
只输出 JSON：{\"intent\":\"QUERY\",\"sql\":\"...\",\"used_tables\":[],\"assumptions\":[]}。
只允许单条 SELECT/WITH，不要猜字段。"""


def read_jsonl(path: Path) -> List[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_question(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def validate(
    rows_by_split: Dict[str, List[Dict[str, object]]],
    database_url: str,
    require_approved: bool = True,
) -> Dict[str, Dict[str, str]]:
    ids = set()
    question_owner = {}
    template_owner = {}
    execution_manifest: Dict[str, Dict[str, str]] = {}
    if database_url.startswith("sqlite:///"):
        runner = SQLiteRunner(database_url[len("sqlite:///") :], max_rows=10000)
    else:
        runner = PostgresRunner(database_url, max_rows=10000, statement_timeout_ms=30000)
    for split, rows in rows_by_split.items():
        for row in rows:
            sample_id = str(row["id"])
            if sample_id in ids:
                raise ValueError(f"duplicate id: {sample_id}")
            ids.add(sample_id)
            if require_approved and row.get("review_status", "approved") != "approved":
                raise ValueError(f"sample is not approved: {sample_id}")
            sql = str(row["sql"])
            sqlglot.parse_one(sql, read="postgres")
            execution = runner.execute(sql)
            if not execution.ok:
                message = execution.error.safe_message if execution.error else "unknown error"
                raise ValueError(f"sample does not execute: {sample_id}: {message}")
            computed_hash = result_hash(
                execution.rows, order_sensitive=bool(row.get("order_sensitive", False))
            )
            expected_hash = row.get("expected_result_hash")
            if expected_hash and str(expected_hash) != computed_hash:
                raise ValueError(f"result hash mismatch: {sample_id}")
            row["expected_result_hash"] = computed_hash
            execution_manifest[sample_id] = {
                "result_hash": computed_hash,
                "row_count": str(len(execution.rows)),
            }
            question_key = normalize_question(str(row["question"]))
            if question_key in question_owner and question_owner[question_key] != split:
                raise ValueError(f"question leakage: {sample_id}")
            question_owner[question_key] = split
            template = str(row["template_group"])
            if template in template_owner and template_owner[template] != split:
                raise ValueError(f"template leakage: {template}")
            template_owner[template] = split
    return execution_manifest


def convert(rows: Iterable[Dict[str, object]]) -> List[Dict[str, str]]:
    converted = []
    for row in rows:
        response = {
            "intent": "QUERY",
            "sql": row["sql"],
            "used_tables": row.get("tables", []),
            "assumptions": [],
        }
        converted.append(
            {
                "instruction": INSTRUCTION,
                "input": f"Schema:\n{row['schema_context']}\n\n问题：{row['question']}",
                "output": json.dumps(response, ensure_ascii=False),
            }
        )
    return converted


def write_json(rows: List[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("training/datasets/raw"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("training/datasets/llamafactory")
    )
    parser.add_argument(
        "--database-url", default="sqlite:///data/snapshots/demo.db"
    )
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    rows = {split: read_jsonl(args.raw_dir / f"{split}.jsonl") for split in ("train", "dev", "blind")}
    execution_manifest = validate(
        rows, args.database_url, require_approved=not args.allow_pending
    )
    train_path = args.output_dir / "text2sql_train_v1.json"
    dev_path = args.output_dir / "text2sql_dev_v1.json"
    write_json(convert(rows["train"]), train_path)
    write_json(convert(rows["dev"]), dev_path)
    manifest = {
        "counts": {split: len(items) for split, items in rows.items()},
        "hashes": {
            split: sha256(args.raw_dir / f"{split}.jsonl") for split in rows
        },
        "blind_split_hashed_and_validated_by_script": True,
        "human_blindness_must_be_enforced_by_process": True,
        "database_url_redacted": args.database_url.split("@")[-1],
        "all_sql_parsed_and_executed": True,
        "execution": execution_manifest,
    }
    with (args.output_dir / "split_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

