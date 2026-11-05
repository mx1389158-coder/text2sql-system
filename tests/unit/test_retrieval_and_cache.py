import json
from pathlib import Path

import pytest

from apps.api.app.schemas.query import QueryRecord, QueryResult, QueryStatus, TraceEvent
from apps.api.app.services.cache import CachedQueryResult, QueryCache, TTLCache
from packages.generation.few_shot import FewShotRetriever
from packages.schema_linker.retriever import SchemaRetriever


def test_hybrid_retriever_returns_confidence_and_columns(catalog):
    evidence = SchemaRetriever(catalog).retrieve("不同型号的平均满意度", top_k=3)
    assert "satisfaction_surveys" in evidence.selected_tables
    assert evidence.selected_columns
    assert 0 <= evidence.confidence <= 1


def test_few_shot_retriever_filters_by_allowed_tables():
    path = Path(__file__).resolve().parents[2] / "training/datasets/raw/train.jsonl"
    retriever = FewShotRetriever(path, limit=2)
    shots = retriever.retrieve("统计产品型号", ["products"])
    assert len(shots) <= 2
    assert all("SQL：" in shot for shot in shots)


def test_few_shot_retriever_diversifies_template_groups(tmp_path):
    path = tmp_path / "train.jsonl"
    rows = [
        {
            "id": "a1",
            "question": "统计2024-01-01以来各工程师上门次数",
            "sql": "SELECT 1",
            "tables": ["service_visits", "agents"],
            "template_group": "agent_visits",
        },
        {
            "id": "a2",
            "question": "统计2024-01-02以来各工程师上门次数",
            "sql": "SELECT 2",
            "tables": ["service_visits", "agents"],
            "template_group": "agent_visits",
        },
        {
            "id": "t1",
            "question": "统计2024-01-03以来各团队上门次数",
            "sql": "SELECT 3",
            "tables": ["service_visits", "agents", "teams"],
            "template_group": "team_visits",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    retriever = FewShotRetriever(path, limit=3)

    shots = retriever.retrieve(
        "统计2026-01-01以来各团队完成的上门次数",
        ["service_visits", "agents", "teams"],
    )

    assert len(shots) == 2
    assert sum("SELECT 1" in shot or "SELECT 2" in shot for shot in shots) == 1
    assert any("SELECT 3" in shot for shot in shots)


def test_few_shot_retriever_prefers_bridge_example(tmp_path):
    path = tmp_path / "train.jsonl"
    rows = [
        {
            "id": "shipment",
            "question": "按配送城市统计已送达记录",
            "sql": "SELECT 1",
            "tables": ["shipments", "customer_addresses"],
            "template_group": "shipments_city",
        },
        {
            "id": "orders",
            "question": "统计各状态订单数",
            "sql": "SELECT 2",
            "tables": ["orders"],
            "template_group": "orders_status",
        },
        {
            "id": "address_region",
            "question": "按地区统计收货地址数量",
            "sql": "SELECT 3",
            "tables": ["customer_addresses", "regions"],
            "template_group": "addresses_region",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    retriever = FewShotRetriever(path, limit=2)

    shots = retriever.retrieve(
        "统计各配送地区已送达的订单数",
        ["shipments", "customer_addresses", "regions", "orders"],
    )

    assert "SELECT 1" in shots[0]
    assert "SELECT 3" in shots[1]


def test_few_shot_retriever_covers_explicit_business_entities(tmp_path):
    path = tmp_path / "train.jsonl"
    rows = [
        {
            "id": "payment",
            "question": "汇总各订单实付金额",
            "sql": "SELECT 'payment'",
            "tables": ["payments", "orders"],
            "template_group": "payment_amount",
        },
        {
            "id": "refund",
            "question": "统计各退款类型申请数",
            "sql": "SELECT 'refund'",
            "tables": ["refunds"],
            "template_group": "refund_type",
        },
        {
            "id": "category",
            "question": "统计各产品分类设备量",
            "sql": "SELECT 'category'",
            "tables": ["products", "product_categories"],
            "template_group": "product_category",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    retriever = FewShotRetriever(path, limit=2)

    shots = retriever.retrieve(
        "汇总各产品分类获批的退款金额",
        ["refunds", "product_categories", "products", "payments", "orders"],
    )

    assert any("SELECT 'refund'" in shot for shot in shots)
    assert any("SELECT 'category'" in shot for shot in shots)


def test_ttl_cache_clear():
    cache = TTLCache[dict](60)
    cache.set("key", {"value": 1})
    value = cache.get("key")
    assert value == {"value": 1}
    value["value"] = 2
    assert cache.get("key") == {"value": 1}
    cache.clear()
    assert cache.get("key") is None


def _query_cache_key(**overrides):
    values = {
        "question": "统计最近 30 天订单金额",
        "clarification": "",
        "schema_version": "schema-v1",
        "scope": "analyst",
        "policy_version": "policy-v1",
        "strategy": "baseline",
        "model_id": "model-v1",
        "prompt_version": "prompt-v1",
        "few_shot_version": "fewshot-v1",
        "semantic_version": "semantic-v1",
        "runtime_version": "runtime-v1",
    }
    values.update(overrides)
    return QueryCache.key(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", "finance_admin"),
        ("policy_version", "policy-v2"),
        ("strategy", "optimized"),
        ("model_id", "model-v2"),
        ("prompt_version", "prompt-v2"),
        ("schema_version", "schema-v2"),
        ("few_shot_version", "fewshot-v2"),
        ("semantic_version", "semantic-v2"),
        ("runtime_version", "runtime-v2"),
        ("clarification", "按支付时间"),
    ],
)
def test_query_cache_key_isolates_runtime_dimensions(field, value):
    assert _query_cache_key(**{field: value}) != _query_cache_key()


def test_query_cache_key_normalizes_equivalent_question_whitespace_and_case():
    assert _query_cache_key(question="  SALES   BY Month ") == _query_cache_key(
        question="sales by month"
    )


def test_cached_value_excludes_request_metadata():
    source = QueryRecord(
        query_id="old-query",
        trace_id="old-trace",
        scope="analyst",
        session_id="old-session",
        question="列出产品",
        status=QueryStatus.COMPLETED,
        sql="SELECT id FROM products",
        result=QueryResult(columns=["id"], rows=[{"id": 1}], elapsed_ms=12.5),
        model_calls=3,
        prompt_tokens=100,
        completion_tokens=20,
        repair_rounds=2,
        repair_succeeded=True,
        trace=[TraceEvent(stage="generation", status="completed")],
    )
    cached = CachedQueryResult.from_record(source)
    request = QueryRecord(
        query_id="new-query",
        trace_id="new-trace",
        scope="analyst",
        session_id="new-session",
        question=source.question,
    )

    cached.apply_to(request)

    assert request.query_id == "new-query"
    assert request.trace_id == "new-trace"
    assert request.session_id == "new-session"
    assert request.model_calls == 0
    assert request.prompt_tokens == 0
    assert request.completion_tokens == 0
    assert request.repair_rounds == 0
    assert request.repair_succeeded is False
    assert request.trace == []
    assert request.result is not None
    assert request.result.elapsed_ms == 0.0
