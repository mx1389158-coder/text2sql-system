from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.app.core.config import Settings
from apps.api.app.repositories import QueryRepository
from apps.api.app.services.orchestrator import Text2SQLOrchestrator
from packages.execution.demo_db import create_demo_database
from packages.execution.guard import GuardPolicy, SQLGuard
from packages.execution.runner import SQLiteRunner
from packages.generation.candidates import CandidateGenerator
from packages.generation.providers import DemoSQLProvider
from packages.schema_linker.catalog import CatalogLoader
from packages.schema_linker.semantic_catalog import SemanticCatalog


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalog():
    return CatalogLoader.from_json(ROOT / "data/processed/catalog_v1.json")


@pytest.fixture
def guard(catalog):
    return SQLGuard(
        GuardPolicy(
            max_rows=200,
            allowed_tables={table.name for table in catalog.tables},
            allowed_columns={
                table.name: {column.name for column in table.columns}
                for table in catalog.tables
            },
            allowed_schemas={"public", "main"},
        )
    )


@pytest.fixture
def demo_db(tmp_path):
    return create_demo_database(tmp_path / "demo.db")


@pytest.fixture
def orchestrator(catalog, guard, demo_db):
    settings = Settings(
        database_url=f"sqlite:///{demo_db}",
        catalog_path=ROOT / "data/processed/catalog_v1.json",
        semantic_catalog_path=ROOT / "data/processed/semantic_catalog_v1.json",
        llm_provider="demo",
        cache_ttl_seconds=0,
    )
    return Text2SQLOrchestrator(
        settings=settings,
        catalog=catalog,
        semantic_catalog=SemanticCatalog.from_json(settings.semantic_catalog_path),
        generator=CandidateGenerator(DemoSQLProvider()),
        guard=guard,
        runner=SQLiteRunner(demo_db),
        repository=QueryRepository(),
    )

