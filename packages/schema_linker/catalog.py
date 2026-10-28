from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import (
    ColumnInfo,
    DatabaseCatalog,
    ForeignKeyInfo,
    TableInfo,
    catalog_from_dict,
)


class CatalogLoader:
    """Load a versioned catalog or introspect one from a SQLAlchemy URL."""

    @staticmethod
    def from_json(path: str | Path) -> DatabaseCatalog:
        with Path(path).open("r", encoding="utf-8") as handle:
            return catalog_from_dict(json.load(handle))

    @staticmethod
    def write_json(catalog: DatabaseCatalog, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(catalog.to_dict(), handle, ensure_ascii=False, indent=2)

    @classmethod
    def from_database(
        cls,
        database_url: str,
        schema: Optional[str] = None,
        database_id: str = "nebula_business",
        version: str = "live",
        sample_values: int = 3,
        include_tables: Optional[Iterable[str]] = None,
    ) -> DatabaseCatalog:
        from sqlalchemy import create_engine, inspect

        engine = create_engine(database_url)
        inspector = inspect(engine)
        effective_schema = schema
        table_names = inspector.get_table_names(schema=effective_schema)
        if include_tables is not None:
            allowed = set(include_tables)
            table_names = [name for name in table_names if name in allowed]

        tables: List[TableInfo] = []
        with engine.connect() as connection:
            for table_name in sorted(table_names):
                pk = set(
                    inspector.get_pk_constraint(table_name, schema=effective_schema).get(
                        "constrained_columns", []
                    )
                )
                raw_fks = inspector.get_foreign_keys(table_name, schema=effective_schema)
                fks = [
                    ForeignKeyInfo(
                        column=fk["constrained_columns"][0],
                        referred_table=fk["referred_table"],
                        referred_column=fk["referred_columns"][0],
                    )
                    for fk in raw_fks
                    if fk.get("constrained_columns") and fk.get("referred_columns")
                ]
                examples = cls._sample_columns(
                    connection, table_name, inspector.get_columns(table_name, schema=effective_schema),
                    schema=effective_schema, sample_values=sample_values
                )
                columns = [
                    ColumnInfo(
                        name=column["name"],
                        data_type=str(column["type"]),
                        nullable=bool(column.get("nullable", True)),
                        primary_key=column["name"] in pk,
                        examples=examples.get(column["name"], []),
                    )
                    for column in inspector.get_columns(table_name, schema=effective_schema)
                ]
                try:
                    comment = inspector.get_table_comment(table_name, schema=effective_schema).get(
                        "text", ""
                    ) or ""
                except NotImplementedError:
                    comment = ""
                tables.append(
                    TableInfo(
                        name=table_name,
                        description=comment,
                        columns=columns,
                        foreign_keys=fks,
                    )
                )
        return DatabaseCatalog(
            database_id=database_id,
            schema=effective_schema or inspector.default_schema_name,
            version=version,
            tables=tables,
        )

    @staticmethod
    def _sample_columns(
        connection: Any,
        table_name: str,
        columns: List[Dict[str, Any]],
        schema: Optional[str],
        sample_values: int,
    ) -> Dict[str, List[Any]]:
        if sample_values <= 0 or not columns:
            return {}
        preparer = connection.dialect.identifier_preparer
        qualified = preparer.quote(table_name)
        if schema:
            qualified = f"{preparer.quote(schema)}.{qualified}"
        result: Dict[str, List[Any]] = {}
        for column in columns:
            name = column["name"]
            quoted = preparer.quote(name)
            from sqlalchemy import text

            statement = text(
                f"SELECT DISTINCT {quoted} FROM {qualified} "
                f"WHERE {quoted} IS NOT NULL LIMIT {int(sample_values)}"
            )
            try:
                result[name] = [row[0] for row in connection.execute(statement)]
            except Exception:
                result[name] = []
        return result

