from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from packages.execution.demo_db import create_demo_database
from packages.execution.access import AccessPolicy
from packages.execution.guard import GuardPolicy, SQLGuard
from packages.execution.runner import PostgresRunner, SQLiteRunner
from packages.generation.candidates import CandidateGenerator
from packages.generation.providers import DemoSQLProvider, OpenAICompatibleProvider
from packages.schema_linker.catalog import CatalogLoader
from packages.schema_linker.semantic_catalog import SemanticCatalog

from .core.config import get_settings
from .repositories import FeedbackRepository, JobRepository, QueryRepository
from .services.orchestrator import Text2SQLOrchestrator


_settings = get_settings()
query_repository = QueryRepository(_settings.state_database_path)
feedback_repository = FeedbackRepository()
job_repository = JobRepository(_settings.state_database_path)


@lru_cache
def get_orchestrator() -> Text2SQLOrchestrator:
    settings = get_settings()
    catalog = CatalogLoader.from_json(settings.catalog_path)
    semantic_catalog = SemanticCatalog.from_json(settings.semantic_catalog_path)
    if settings.llm_provider == "demo":
        provider = DemoSQLProvider()
    else:
        provider = OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.model_timeout_seconds,
            parse_retries=settings.model_parse_retries,
            max_tokens=settings.model_max_tokens,
        )
    if settings.database_url.startswith("sqlite:///"):
        raw_path = settings.database_url.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        if not db_path.exists():
            create_demo_database(db_path)
        runner = SQLiteRunner(
            db_path, max_rows=settings.max_rows, timeout_ms=settings.statement_timeout_ms
        )
    else:
        runner = PostgresRunner(
            settings.database_url,
            max_rows=settings.max_rows,
            statement_timeout_ms=settings.statement_timeout_ms,
            lock_timeout_ms=settings.lock_timeout_ms,
        )
    guard = SQLGuard(
        GuardPolicy(
            max_rows=settings.max_rows,
            allowed_tables={table.name for table in catalog.tables},
            allowed_schemas={catalog.schema},
        )
    )
    access_policy = AccessPolicy.from_json(
        settings.access_policy_path,
        {table.name for table in catalog.tables},
        catalog.schema,
    )
    return Text2SQLOrchestrator(
        settings=settings,
        catalog=catalog,
        semantic_catalog=semantic_catalog,
        generator=CandidateGenerator(provider),
        guard=guard,
        runner=runner,
        repository=query_repository,
        access_policy=access_policy,
    )

