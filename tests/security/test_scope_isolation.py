from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.dependencies import get_orchestrator
from apps.api.app.main import app
from apps.api.app.repositories import FeedbackRepository, QueryRepository
from apps.api.app.routers import feedback as feedback_router
from apps.api.app.routers import query as query_router
from apps.api.app.schemas.query import QueryRecord, QueryStatus
from packages.execution.access import AccessPolicy
from packages.schema_linker.catalog import CatalogLoader


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def scoped_api(monkeypatch, tmp_path):
    repository = QueryRepository(tmp_path / "state.db")
    feedback = FeedbackRepository(tmp_path / "feedback.jsonl")
    monkeypatch.setattr(query_router, "query_repository", repository)
    monkeypatch.setattr(feedback_router, "query_repository", repository)
    monkeypatch.setattr(feedback_router, "feedback_repository", feedback)

    policy_path = tmp_path / "access.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": "test",
                "scopes": {
                    "restricted_analyst": {
                        "schemas": ["public"],
                        "tables": ["products"],
                        "columns": {"products": ["id", "model_code"]},
                        "sample_values": {},
                    },
                    "analyst": {
                        "schemas": ["public"],
                        "tables": ["orders"],
                        "sample_values": {},
                    },
                    "finance_admin": {
                        "schemas": ["public"],
                        "tables": ["*"],
                        "sample_values": {"*": ["*"]},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    catalog = CatalogLoader.from_json(ROOT / "data/processed/catalog_v1.json")
    access_policy = AccessPolicy.from_json(
        policy_path, {table.name for table in catalog.tables}, catalog.schema
    )

    settings = Settings(
        api_keys_json=json.dumps(
            {
                "attacker-key": "restricted_analyst",
                "analyst-key": "analyst",
                "admin-key": "finance_admin",
            }
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: SimpleNamespace(
        catalog=catalog,
        access_policy=access_policy,
    )
    try:
        yield TestClient(app), repository
    finally:
        app.dependency_overrides.clear()


def _record(query_id: str, scope: str, status=QueryStatus.COMPLETED) -> QueryRecord:
    return QueryRecord(
        query_id=query_id,
        trace_id=f"trace-{query_id}",
        scope=scope,
        question=f"question-{query_id}",
        status=status,
        sql="SELECT 1",
    )


def test_query_detail_returns_404_across_scopes(scoped_api):
    client, repository = scoped_api
    repository.save(_record("finance-query", "finance_admin"))

    hidden = client.get(
        "/api/v1/query/finance-query", headers={"X-API-Key": "attacker-key"}
    )
    owner = client.get(
        "/api/v1/query/finance-query", headers={"X-API-Key": "admin-key"}
    )

    assert hidden.status_code == 404
    assert owner.status_code == 200
    assert owner.json()["scope"] == "finance_admin"


def test_query_list_is_filtered_by_current_scope(scoped_api):
    client, repository = scoped_api
    repository.save(_record("restricted-query", "restricted_analyst"))
    repository.save(_record("analyst-query", "analyst"))
    repository.save(_record("finance-query", "finance_admin"))

    attacker_items = client.get(
        "/api/v1/queries", headers={"X-API-Key": "attacker-key"}
    ).json()["items"]
    analyst_items = client.get(
        "/api/v1/queries", headers={"X-API-Key": "analyst-key"}
    ).json()["items"]
    admin_items = client.get(
        "/api/v1/queries", headers={"X-API-Key": "admin-key"}
    ).json()["items"]

    assert {item["query_id"] for item in attacker_items} == {"restricted-query"}
    assert {item["query_id"] for item in analyst_items} == {"analyst-query"}
    assert {item["query_id"] for item in admin_items} == {"finance-query"}


def test_clarification_and_feedback_cannot_cross_scope(scoped_api):
    client, repository = scoped_api
    repository.save(
        _record(
            "finance-clarification",
            "finance_admin",
            status=QueryStatus.CLARIFICATION_REQUIRED,
        )
    )

    clarification = client.post(
        "/api/v1/query/finance-clarification/clarify",
        headers={"X-API-Key": "attacker-key"},
        json={"answer": "按支付时间"},
    )
    feedback = client.post(
        "/api/v1/feedback",
        headers={"X-API-Key": "attacker-key"},
        json={"query_id": "finance-clarification", "rating": "incorrect"},
    )

    assert clarification.status_code == 404
    assert feedback.status_code == 404


def test_schema_catalog_is_filtered_by_scope(scoped_api):
    client, _ = scoped_api

    restricted = client.get(
        "/api/v1/schema", headers={"X-API-Key": "attacker-key"}
    ).json()
    admin = client.get(
        "/api/v1/schema", headers={"X-API-Key": "admin-key"}
    ).json()

    assert [table["name"] for table in restricted["tables"]] == ["products"]
    assert {column["name"] for column in restricted["tables"][0]["columns"]} == {
        "id",
        "model_code",
    }
    assert all(
        column["examples"] == [] for column in restricted["tables"][0]["columns"]
    )
    assert len(admin["tables"]) == 23
    assert any(
        column["examples"]
        for table in admin["tables"]
        for column in table["columns"]
    )
