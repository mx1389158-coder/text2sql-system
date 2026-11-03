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
    template_group: str
    vector: List[float]


class FewShotRetriever:
    _QUESTION_TABLE_MARKERS = {
        "退款": {"refunds"},
        "分类": {"product_categories", "products"},
        "品类": {"product_categories", "products"},
        "配送": {"shipments", "customer_addresses"},
        "送达": {"shipments"},
        "地区": {"regions"},
        "升级": {"device_upgrades"},
        "团队": {"teams", "agents"},
        "上门": {"service_visits"},
        "保修": {"warranties"},
        "质保": {"warranties"},
        "型号": {"products"},
    }

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
                            template_group=str(
                                row.get("template_group") or f"ungrouped:{row.get('id', question)}"
                            ),
                            vector=self.encoder.encode(question),
                        )
                    )
        return result

    def retrieve(self, question: str, allowed_tables: List[str]) -> List[str]:
        if not self.examples:
            return []
        query_vector = self.encoder.encode(question)
        allowed = set(allowed_tables)
        intent_tables = {
            table
            for marker, tables in self._QUESTION_TABLE_MARKERS.items()
            if marker in question
            for table in tables
        }
        table_priority = {
            table: 1.0 / (index + 1) for index, table in enumerate(allowed_tables)
        }
        candidates = [
            item
            for item in self.examples
            if item.question.strip().lower() != question.strip().lower()
            and (not item.tables or set(item.tables).issubset(allowed))
        ]
        selected = []
        selected_groups = set()
        covered_tables = set()
        while candidates and len(selected) < self.limit:
            eligible = [
                item
                for item in candidates
                if item.template_group not in selected_groups
            ]
            if not eligible:
                break

            def relevance(item: FewShotExample) -> tuple[float, float]:
                semantic = self.encoder.cosine(query_vector, item.vector)
                tables = set(item.tables)
                new_tables = tables - covered_tables
                bridge_bonus = 0.35 if covered_tables & tables and new_tables else 0.0
                coverage_bonus = 0.05 * sum(
                    table_priority.get(table, 0.0) for table in new_tables
                )
                intent_bonus = 0.25 * len(tables & intent_tables)
                return semantic + bridge_bonus + coverage_bonus + intent_bonus, semantic

            item = max(eligible, key=relevance)
            selected.append(f"问题：{item.question}\nSQL：{item.sql}")
            selected_groups.add(item.template_group)
            covered_tables.update(item.tables)
            candidates.remove(item)
        return selected
