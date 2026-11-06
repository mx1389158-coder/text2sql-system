from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.dependencies import get_orchestrator
from apps.api.app.main import app
from apps.api.app.repositories import JobRepository
from apps.api.app.routers import evals as evals_router


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def evaluation_api(monkeypatch, tmp_path):
    repository = JobRepository(tmp_path / "state.db")
    monkeypatch.setattr(evals_router, "job_repository", repository)
    monkeypatch.setattr(evals_router, "_schedule", lambda *args, **kwargs: None)
    settings = Settings(
        api_keys_json=json.dumps(
            {
                "attacker-key": "restricted_analyst",
                "evaluation-key": "evaluation",
            }
        ),
        evaluation_allowed_root=ROOT / "data",
        max_active_evaluation_jobs=1,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: SimpleNamespace()
    try:
        yield TestClient(app), repository
    finally:
        app.dependency_overrides.clear()


def _payload(strategy: str = "optimized") -> dict[str, str]:
    return {
        "dataset_path": str(ROOT / "data/processed/smoke.jsonl"),
        "model": "demo",
        "strategy": strategy,
    }


def test_restricted_scope_cannot_access_evaluation_endpoints(evaluation_api):
    client, _ = evaluation_api
    headers = {"X-API-Key": "attacker-key"}

    assert client.post("/api/v1/evals/run", headers=headers, json=_payload()).status_code == 403
    assert client.get("/api/v1/evals", headers=headers).status_code == 403
    assert client.get("/api/v1/evals/unknown", headers=headers).status_code == 403


def test_evaluation_scope_can_create_and_read_own_job(evaluation_api):
    client, _ = evaluation_api
    headers = {"X-API-Key": "evaluation-key"}

    created = client.post("/api/v1/evals/run", headers=headers, json=_payload())

    assert created.status_code == 202
    job_id = created.json()["job_id"]
    detail = client.get(f"/api/v1/evals/{job_id}", headers=headers)
    listing = client.get("/api/v1/evals", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["scope"] == "evaluation"
    assert [job["job_id"] for job in listing.json()["jobs"]] == [job_id]


def test_evaluation_active_job_limit_returns_429(evaluation_api):
    client, _ = evaluation_api
    headers = {"X-API-Key": "evaluation-key"}

    assert client.post("/api/v1/evals/run", headers=headers, json=_payload()).status_code == 202
    limited = client.post("/api/v1/evals/run", headers=headers, json=_payload())

    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "5"


def test_invalid_strategy_is_rejected_with_422(evaluation_api):
    client, _ = evaluation_api

    eval_response = client.post(
        "/api/v1/evals/run",
        headers={"X-API-Key": "evaluation-key"},
        json=_payload("not-a-strategy"),
    )
    query_response = client.post(
        "/api/v1/query",
        headers={"X-API-Key": "attacker-key"},
        json={"question": "count orders", "strategy": "not-a-strategy"},
    )

    assert eval_response.status_code == 422
    assert query_response.status_code == 422
