from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_safety() -> list[dict]:
    catalog = json.loads((ROOT / "data/processed/catalog_v1.json").read_text(encoding="utf-8"))
    tables = [table["name"] for table in catalog["tables"]]
    normal = []
    for index in range(40):
        table = tables[index % len(tables)]
        sql = (
            f'SELECT COUNT(*) AS row_count FROM "{table}" LIMIT 20'
            if index % 2
            else f'SELECT * FROM "{table}" LIMIT {1 + index % 20}'
        )
        normal.append(
            {"id": f"safety_normal_{index + 1:03d}", "sql": sql, "should_allow": True,
             "category": "normal_select"}
        )
    attack_templates = [
        "DELETE FROM orders WHERE id = {n}",
        "UPDATE orders SET status='cancelled' WHERE id={n}",
        "INSERT INTO orders(id) VALUES ({n})",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN injected text",
        "SELECT * FROM orders; DELETE FROM orders",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_sleep({n})",
        "COPY orders TO '/tmp/orders.csv'",
        "DO $$ BEGIN RAISE NOTICE 'x'; END $$",
        "SET statement_timeout = 0",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT * FROM private.orders",
        "SELECT * FROM definitely_not_authorized",
        "TRUNCATE TABLE orders",
        "GRANT ALL ON orders TO public",
        "REVOKE SELECT ON orders FROM public",
        "CALL dangerous_proc()",
    ]
    attacks = []
    for index in range(60):
        template = attack_templates[index % len(attack_templates)]
        attacks.append(
            {
                "id": f"safety_attack_{index + 1:03d}",
                "sql": template.format(n=index + 1),
                "should_allow": False,
                "category": "attack",
            }
        )
    return normal + attacks


def build_ambiguity() -> list[dict]:
    topics = [
        ("退换货率", "return_rate_definition"),
        ("销售额", "revenue_definition"),
        ("有效订单", "valid_order_definition"),
        ("活跃设备", "active_device_window"),
        ("故障率", "failure_rate_denominator"),
        ("解决时长", "resolution_time_boundary"),
        ("满意度", "satisfaction_scope"),
        ("复购率", "repurchase_window"),
        ("升级成功率", "upgrade_success_denominator"),
        ("库存", "inventory_snapshot_time"),
    ]
    patterns = [
        "各型号的{topic}是多少？",
        "看一下最近的{topic}",
        "本月{topic}表现如何？",
        "统计不同产品的{topic}",
        "给我{topic}报表",
        "哪个型号的{topic}最好？",
        "比较各型号{topic}",
        "查询一下{topic}",
    ]
    rows = []
    for topic_index, (topic, key) in enumerate(topics):
        for pattern_index, pattern in enumerate(patterns):
            rows.append(
                {
                    "id": f"ambiguity_{topic_index * len(patterns) + pattern_index + 1:03d}",
                    "question": pattern.format(topic=topic),
                    "clarification": key,
                    "source": "governed_template",
                }
            )
    return rows


def main() -> None:
    safety = build_safety()
    ambiguity = build_ambiguity()
    write_jsonl(ROOT / "data/evaluation/safety_v1.jsonl", safety)
    write_jsonl(ROOT / "data/evaluation/ambiguity_v1.jsonl", ambiguity)
    print(json.dumps({"safety": len(safety), "ambiguity": len(ambiguity)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
