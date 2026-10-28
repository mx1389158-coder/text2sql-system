from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    description: str = ""
    nullable: bool = True
    primary_key: bool = False
    examples: List[Any] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForeignKeyInfo:
    column: str
    referred_table: str
    referred_column: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    description: str
    columns: List[ColumnInfo]
    foreign_keys: List[ForeignKeyInfo] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatabaseCatalog:
    database_id: str
    schema: str
    version: str
    tables: List[TableInfo]

    @property
    def table_map(self) -> Dict[str, TableInfo]:
        return {table.name: table for table in self.tables}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ColumnEvidence:
    table: str
    column: str
    score: float


@dataclass(frozen=True)
class SchemaEvidence:
    selected_tables: List[str]
    table_scores: Dict[str, float]
    selected_columns: List[ColumnEvidence]
    join_path_tables: List[str]
    mschema: str = ""
    estimated_tokens: int = 0
    expanded: bool = False
    confidence: float = 0.0


def catalog_from_dict(payload: Dict[str, Any]) -> DatabaseCatalog:
    tables: List[TableInfo] = []
    for raw_table in payload.get("tables", []):
        columns = [ColumnInfo(**column) for column in raw_table.get("columns", [])]
        foreign_keys = [ForeignKeyInfo(**fk) for fk in raw_table.get("foreign_keys", [])]
        tables.append(
            TableInfo(
                name=raw_table["name"],
                description=raw_table.get("description", ""),
                columns=columns,
                foreign_keys=foreign_keys,
                aliases=raw_table.get("aliases", []),
            )
        )
    return DatabaseCatalog(
        database_id=payload.get("database_id", "unknown"),
        schema=payload.get("schema", "public"),
        version=payload.get("version", "unversioned"),
        tables=tables,
    )

