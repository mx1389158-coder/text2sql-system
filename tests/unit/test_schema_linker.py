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

