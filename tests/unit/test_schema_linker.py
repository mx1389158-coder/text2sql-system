import json
from pathlib import Path

from packages.schema_linker.semantic_catalog import SemanticCatalog
from packages.schema_linker.mschema import MSchemaFormatter
from packages.schema_linker.retriever import SchemaRetriever


def test_retrieves_business_tables_and_join_paths(catalog):
    evidence = SchemaRetriever(catalog).retrieve("按产品型号统计重复报修和故障类型", top_k=4)
    assert "tickets" in evidence.selected_tables
    assert "products" in evidence.selected_tables
    assert "devices" in evidence.selected_tables


def test_mschema_contains_columns_and_foreign_keys(catalog):
    retriever = SchemaRetriever(catalog)
    evidence = retriever.retrieve("产品型号和订单明细", top_k=4)
    rendered = MSchemaFormatter(catalog).format(evidence, token_budget=3000)
    assert "# Table:" in rendered.mschema
    assert "[Foreign keys]" in rendered.mschema
    assert rendered.estimated_tokens <= 3000


def test_mschema_filters_hidden_columns_and_sample_values(catalog):
    evidence = SchemaRetriever(catalog).retrieve("产品型号和名称", top_k=2)
    rendered = MSchemaFormatter(catalog).format(
        evidence,
        token_budget=3000,
        allowed_columns={"products": {"model_code"}},
        sample_value_allowed=lambda _table, _column: False,
    )

    assert "model_code:" in rendered.mschema
    assert "list_price:" not in rendered.mschema
    assert "Examples:" not in rendered.mschema


def test_ambiguity_requires_complete_business_alias():
    catalog = SemanticCatalog.from_json("data/processed/semantic_catalog_v1.json")

    assert catalog.ambiguity("按型号统计结束保修的设备量") is None
    assert catalog.ambiguity("统计有效订单") is not None


def test_governed_ambiguity_set_matches_all_expected_keys():
    root = Path(__file__).resolve().parents[2]
    catalog = SemanticCatalog.from_json(root / "data/processed/semantic_catalog_v1.json")
    rows = [
        json.loads(line)
        for line in (root / "data/evaluation/ambiguity_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) == 80
    for row in rows:
        ambiguity = catalog.ambiguity(row["question"])
        assert ambiguity is not None, row["id"]
        assert ambiguity["key"] == row["clarification"], row["id"]


def test_explicit_metric_scope_does_not_trigger_false_clarification():
    catalog = SemanticCatalog.from_json("data/processed/semantic_catalog_v1.json")
    assert catalog.ambiguity("不同型号的平均满意度和评价数") is None
    assert catalog.ambiguity("各仓库所在地区总库存不超过 10 的型号") is None


def test_repeat_ticket_rate_has_a_versioned_clarification_policy():
    catalog = SemanticCatalog.from_json("data/processed/semantic_catalog_v1.json")
    ambiguity = catalog.ambiguity("各型号重复报修率是多少？")

    assert ambiguity is not None
    assert ambiguity["key"] == "repeat_ticket_rate"


def test_semantic_definitions_do_not_match_single_chinese_character_overlap():
    catalog = SemanticCatalog.from_json("data/processed/semantic_catalog_v1.json")

    assert catalog.retrieve("按型号统计结束保修的设备量") == []
    assert [item.key for item in catalog.retrieve("统计重复报修")] == [
        "repeat_ticket"
    ]

