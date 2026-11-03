from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_FIELDS = {
    "id",
    "question",
    "sql",
    "tables",
    "template_group",
    "difficulty",
    "snapshot_id",
    "review_status",
}


def normalized_question(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Text2SQL split leakage and stratification metadata"
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("training/datasets/raw"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/data_card/dataset_governance_report.json"),
    )
    args = parser.parse_args()

    splits = {
        name: read_jsonl(args.raw_dir / f"{name}.jsonl")
        for name in ("train", "dev", "blind")
    }
    id_owner: dict[str, str] = {}
    question_owner: dict[str, str] = {}
    template_owner: dict[str, str] = {}
    leaks: list[dict[str, str]] = []
    missing_metadata: list[str] = []
    distributions = {}

    for split, rows in splits.items():
        difficulty = Counter()
        table_combinations = Counter()
        templates = Counter()
        sources = Counter()
        for row in rows:
            sample_id = str(row.get("id", ""))
            missing = sorted(REQUIRED_FIELDS - set(row))
            if missing:
                missing_metadata.append(f"{sample_id}:{','.join(missing)}")
            question = normalized_question(str(row.get("question", "")))
            template = str(row.get("template_group", ""))
            for kind, key, owners in (
                ("id", sample_id, id_owner),
                ("question", question, question_owner),
                ("template_group", template, template_owner),
            ):
                previous = owners.get(key)
                if previous is not None and previous != split:
                    leaks.append({"kind": kind, "key": key, "left": previous, "right": split})
                owners[key] = split
            difficulty[str(row.get("difficulty"))] += 1
            table_combinations["+".join(sorted(map(str, row.get("tables", []))))] += 1
            templates[template] += 1
            sources[str(row.get("source"))] += 1
        distributions[split] = {
            "count": len(rows),
            "difficulty": dict(sorted(difficulty.items())),
            "template_family_count": len(templates),
            "table_combination_count": len(table_combinations),
            "template_groups": dict(sorted(templates.items())),
            "table_combinations": dict(sorted(table_combinations.items())),
            "sources": dict(sorted(sources.items())),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not leaks and not missing_metadata else "failed",
        "rules": {
            "cross_split_id_leakage": "forbidden",
            "cross_split_normalized_question_leakage": "forbidden",
            "cross_split_template_group_leakage": "forbidden",
            "stratification_dimensions": [
                "business semantic template",
                "table combination",
                "difficulty",
            ],
        },
        "leaks": leaks,
        "missing_metadata": missing_metadata,
        "distributions": distributions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
