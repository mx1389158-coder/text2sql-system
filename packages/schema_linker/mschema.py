from __future__ import annotations

from dataclasses import replace
from typing import Callable, Dict, List, Optional, Set

from .models import DatabaseCatalog, SchemaEvidence


class MSchemaFormatter:
    """Our compact schema format, inspired by M-Schema but with a local data model."""

    def __init__(self, catalog: DatabaseCatalog):
        self.catalog = catalog

    def format(
        self,
        evidence: SchemaEvidence,
        token_budget: int = 3000,
        examples_per_column: int = 2,
        allowed_columns: Optional[Dict[str, Set[str]]] = None,
        sample_value_allowed: Optional[Callable[[str, str], bool]] = None,
    ) -> SchemaEvidence:
        selected_columns: Dict[str, Set[str]] = {}
        for column in evidence.selected_columns:
            selected_columns.setdefault(column.table, set()).add(column.column)

        lines: List[str] = [
            f"[Database] {self.catalog.database_id}",
            f"[Schema] {self.catalog.schema}",
            f"[Version] {self.catalog.version}",
        ]
        foreign_key_lines: List[str] = []
        for table_name in evidence.selected_tables:
            table = self.catalog.table_map[table_name]
            header = f"# Table: {table.name}"
            if table.description:
                header += f" - {table.description}"
            block = [header, "["]
            chosen = selected_columns.get(table_name, set())
            for column in table.columns:
                if allowed_columns is not None and column.name not in allowed_columns.get(
                    table_name, set()
                ):
                    continue
                if chosen and column.name not in chosen and not column.primary_key:
                    continue
                attributes = [f"{column.name}:{column.data_type.upper()}"]
                if column.description:
                    attributes.append(column.description)
                if column.primary_key:
                    attributes.append("Primary Key")
                examples = (
                    [str(value)[:40] for value in column.examples[:examples_per_column]]
                    if sample_value_allowed is None
                    or sample_value_allowed(table_name, column.name)
                    else []
                )
                if examples:
                    attributes.append(f"Examples: [{', '.join(examples)}]")
                block.append(f"  ({', '.join(attributes)}),")
            block.append("]")
            candidate = "\n".join(lines + block + foreign_key_lines)
            if self._estimate_tokens(candidate) > token_budget:
                break
            lines.extend(block)
            for foreign_key in table.foreign_keys:
                if foreign_key.referred_table in evidence.selected_tables:
                    foreign_key_lines.append(
                        f"{table.name}.{foreign_key.column}="
                        f"{foreign_key.referred_table}.{foreign_key.referred_column}"
                    )
        if foreign_key_lines:
            lines.append("[Foreign keys]")
            lines.extend(sorted(set(foreign_key_lines)))
        result = "\n".join(lines)
        return replace(
            evidence,
            mschema=result,
            estimated_tokens=self._estimate_tokens(result),
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        return max(1, (len(text) - chinese) // 4 + chinese)

