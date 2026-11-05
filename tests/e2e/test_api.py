from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.api_key:
        return {"X-API-Key": settings.api_key}
    scoped_keys = settings.api_key_scopes()
    return {"X-API-Key": next(iter(scoped_keys))} if scoped_keys else {}


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_system_endpoint_exposes_safe_runtime_metadata():
    response = TestClient(app).get("/api/v1/system")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "demo"
    assert payload["model"] == "demo"
    assert payload["database_engine"] == "sqlite"
    assert payload["security"] == {"ast_guard": True, "read_only": True, "row_limit": 200}


def test_query_endpoint_runs_complete_pipeline():
    response = TestClient(app).post(
        "/api/v1/query",
        headers=_auth_headers(),
        json={"question": "列出产品型号、名称和价格", "strategy": "optimized"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["prompt_version"] == "text2sql-system-v1.0.0"
    assert len(payload["result"]["rows"]) == 2
    assert "products" in payload["schema_evidence"]["selected_tables"]


def test_clarification_endpoint_resumes_state_machine():
    client = TestClient(app)
    initial = client.post(
        "/api/v1/query",
        headers=_auth_headers(),
        json={"question": "近三个月各型号退换货率是多少？"},
    ).json()
    assert initial["status"] == "clarification_required"
    resumed = client.post(
        f"/api/v1/query/{initial['query_id']}/clarify",
        headers=_auth_headers(),
        json={"answer": "按申请时间，仅退货/换货"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["query_id"] == initial["query_id"]


def test_sse_emits_stage_events_before_result():
    client = TestClient(app)
    response = client.post(
        "/api/v1/query?stream=true",
        headers=_auth_headers(),
        json={"question": "列出产品型号、名称和价格"},
    )
    body = response.text
    assert body.index("event: accepted") < body.index("event: stage") < body.index("event: result")

