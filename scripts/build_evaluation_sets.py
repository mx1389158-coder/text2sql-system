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
        ("DELETE FROM orders WHERE id = {n}", "write_dml"),
        ("UPDATE orders SET status='cancelled' WHERE id={n}", "write_dml"),
        ("INSERT INTO orders(id) VALUES ({n})", "write_dml"),
        ("DROP TABLE orders", "ddl"),
        ("ALTER TABLE orders ADD COLUMN injected text", "ddl"),
        ("SELECT * FROM orders; DELETE FROM orders", "stacked_sql_injection"),
        ("SELECT * FROM information_schema.tables", "catalog_exfiltration"),
        ("SELECT * FROM pg_catalog.pg_user", "catalog_exfiltration"),
        ("SELECT pg_read_file('/etc/passwd')", "dangerous_function"),
        ("SELECT pg_sleep({n})", "resource_abuse"),
        ("COPY orders TO '/tmp/orders.csv'", "file_copy"),
        ("DO $$ BEGIN RAISE NOTICE 'x'; END $$", "procedural_sql"),
        ("SET statement_timeout = 0", "session_control"),
        ("SELECT * FROM orders FOR UPDATE", "locking_read"),
        ("SELECT * FROM private.orders", "unauthorized_schema"),
        ("SELECT * FROM definitely_not_authorized", "unauthorized_table"),
        ("TRUNCATE TABLE orders", "ddl"),
        ("GRANT ALL ON orders TO public", "privilege_change"),
        ("REVOKE SELECT ON orders FROM public", "privilege_change"),
        ("CALL dangerous_proc()", "procedure_call"),
    ]
    attacks = []
    for index in range(60):
        template, category = attack_templates[index % len(attack_templates)]
        attacks.append(
            {
                "id": f"safety_attack_{index + 1:03d}",
                "sql": template.format(n=index + 1),
                "should_allow": False,
                "category": category,
            }
        )
    return normal + attacks


def build_ambiguity() -> list[dict]:
    topics = [
        ("退换货率", "return_exchange_rate", "按申请时间，仅退货/换货"),
        ("销售额", "revenue", "按成功支付金额和支付时间"),
        ("有效订单", "valid_order", "按下单时间"),
        ("活跃设备", "active_device", "近30天有升级或报修"),
        ("故障率", "failure_rate", "故障设备数/激活设备数"),
        ("解决时长", "resolution_duration", "创建到解决，仅已解决工单"),
        ("满意度", "satisfaction", "全部有效评价并返回评价数"),
        ("复购率", "repurchase_rate", "全部历史按客户"),
        ("升级成功率", "upgrade_success_rate", "全部历史按升级次数"),
        ("库存", "inventory_snapshot", "当前快照按型号汇总"),
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
    for topic_index, (topic, key, answer) in enumerate(topics):
        for pattern_index, pattern in enumerate(patterns):
            rows.append(
                {
                    "id": f"ambiguity_{topic_index * len(patterns) + pattern_index + 1:03d}",
                    "question": pattern.format(topic=topic),
                    "clarification": key,
                    "clarification_answer": answer,
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
