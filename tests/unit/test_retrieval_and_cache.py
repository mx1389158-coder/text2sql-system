from pathlib import Path

from apps.api.app.services.cache import TTLCache
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


def test_ttl_cache_clear():
    cache = TTLCache[dict](60)
    cache.set("key", {"value": 1})
    value = cache.get("key")
    assert value == {"value": 1}
    value["value"] = 2
    assert cache.get("key") == {"value": 1}
    cache.clear()
    assert cache.get("key") is None
