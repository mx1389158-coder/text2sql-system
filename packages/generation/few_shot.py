from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from packages.schema_linker.vector import HashingTextEncoder


@dataclass(frozen=True)
class FewShotExample:
    question: str
    sql: str
    tables: List[str]
    vector: List[float]


class FewShotRetriever:
    def __init__(self, path: str | Path, limit: int = 3):
        self.path = Path(path)
        self.limit = max(0, limit)
        self.encoder = HashingTextEncoder()
        self.examples = self._load()

    def _load(self) -> List[FewShotExample]:
        if not self.path.exists() or self.limit == 0:
            return []
        result: List[FewShotExample] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if row.get("review_status", "approved") != "approved":
                    continue
                question = str(row.get("question", "")).strip()
                sql = str(row.get("sql", "")).strip()
                if question and sql:
                    result.append(
                        FewShotExample(
                            question=question,
                            sql=sql,
                            tables=list(row.get("tables") or []),
                            vector=self.encoder.encode(question),
                        )
                    )
        return result

    def retrieve(self, question: str, allowed_tables: List[str]) -> List[str]:
        if not self.examples:
            return []
        query_vector = self.encoder.encode(question)
        allowed = set(allowed_tables)
        ranked = sorted(
            self.examples,
            key=lambda item: self.encoder.cosine(query_vector, item.vector),
            reverse=True,
        )
        selected = []
        for item in ranked:
            if item.question.strip().lower() == question.strip().lower():
                continue
            if item.tables and not set(item.tables).issubset(allowed):
                continue
            selected.append(f"问题：{item.question}\nSQL：{item.sql}")
            if len(selected) >= self.limit:
                break
        return selected
