from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set


@dataclass(frozen=True)
class ScopePolicy:
    schemas: Set[str]
    tables: Set[str]
    columns: Dict[str, Set[str]] = field(default_factory=dict)
    sample_values: Dict[str, Set[str]] = field(default_factory=dict)

    def allowed_columns(self, table: str, catalog_columns: Set[str]) -> Set[str]:
        configured = self.columns.get(table.lower()) or self.columns.get("*")
        if not configured or "*" in configured:
            return set(catalog_columns)
        return {column.lower() for column in catalog_columns} & configured

    def allows_sample_value(self, table: str, column: str) -> bool:
        configured = self.sample_values.get(table.lower()) or self.sample_values.get("*")
        return bool(configured and ("*" in configured or column.lower() in configured))


class AccessPolicy:
    def __init__(self, scopes: Dict[str, ScopePolicy], all_tables: Set[str], default_schema: str):
        self.scopes = scopes
        self.all_tables = {item.lower() for item in all_tables}
        self.default_schema = default_schema.lower()

    @classmethod
    def from_json(
        cls, path: str | Path, all_tables: Set[str], default_schema: str
    ) -> "AccessPolicy":
        target = Path(path)
        if not target.exists():
            return cls({}, all_tables, default_schema)
        payload = json.loads(target.read_text(encoding="utf-8"))
        scopes = {}
        for name, raw in payload.get("scopes", {}).items():
            tables = {str(item).lower() for item in raw.get("tables", [])}
            schemas = {str(item).lower() for item in raw.get("schemas", [default_schema])}
            columns = {
                str(table).lower(): {str(column).lower() for column in items}
                for table, items in raw.get("columns", {}).items()
            }
            sample_values = {
                str(table).lower(): {str(column).lower() for column in items}
                for table, items in raw.get("sample_values", {}).items()
            }
            scopes[str(name)] = ScopePolicy(
                schemas=schemas,
                tables=tables,
                columns=columns,
                sample_values=sample_values,
            )
        return cls(scopes, all_tables, default_schema)

    def resolve(self, scope: str) -> ScopePolicy:
        policy = self.scopes.get(scope) or self.scopes.get("default")
        if policy is None:
            return ScopePolicy(
                schemas={self.default_schema},
                tables=set(self.all_tables),
                sample_values={"*": {"*"}},
            )
        tables = self.all_tables if "*" in policy.tables else policy.tables & self.all_tables
        return ScopePolicy(
            schemas=policy.schemas,
            tables=tables,
            columns=policy.columns,
            sample_values=policy.sample_values,
        )
