from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTRUCTION = """根据给定的 PostgreSQL Schema 和中文问题生成 SQL。
只输出 JSON：{\"intent\":\"QUERY\",\"sql\":\"...\",\"used_tables\":[],\"assumptions\":[]}。
只允许单条 SELECT/WITH，不要猜字段。"""


TEMPLATES = [
    ("产品型号与名称", "products(model_code,name)",
     "SELECT model_code, name FROM products ORDER BY model_code LIMIT 200", ["products"]),
    ("产品型号与价格", "products(model_code,list_price)",
     "SELECT model_code, list_price FROM products ORDER BY model_code LIMIT 200", ["products"]),
    ("有效订单总数", "orders(status)",
     "SELECT COUNT(*) AS order_count FROM orders WHERE status IN ('paid','completed')", ["orders"]),
    ("各型号设备数", "devices(product_id); products(id,model_code)",
     "SELECT p.model_code, COUNT(*) AS device_count FROM devices d JOIN products p ON p.id=d.product_id GROUP BY p.model_code ORDER BY device_count DESC LIMIT 200", ["devices", "products"]),
    ("已解决工单总数", "tickets(status)",
     "SELECT COUNT(*) AS resolved_ticket_count FROM tickets WHERE status='resolved'", ["tickets"]),
    ("各型号平均满意度", "satisfaction_surveys; tickets; devices; products",
     "SELECT p.model_code, ROUND(AVG(s.score),2) AS avg_score FROM satisfaction_surveys s JOIN tickets t ON t.id=s.ticket_id JOIN devices d ON d.id=t.device_id JOIN products p ON p.id=d.product_id GROUP BY p.model_code ORDER BY avg_score DESC LIMIT 200", ["satisfaction_surveys", "tickets", "devices", "products"]),
    ("各型号库存总量", "inventory; products",
     "SELECT p.model_code, SUM(i.quantity) AS inventory_quantity FROM inventory i JOIN products p ON p.id=i.product_id GROUP BY p.model_code ORDER BY inventory_quantity DESC LIMIT 200", ["inventory", "products"]),
    ("升级任务状态分布", "upgrade_jobs(status)",
     "SELECT status, COUNT(*) AS job_count FROM upgrade_jobs GROUP BY status ORDER BY job_count DESC LIMIT 200", ["upgrade_jobs"]),
    ("已批准退款数量", "refunds(status)",
     "SELECT COUNT(*) AS approved_refund_count FROM refunds WHERE status='approved'", ["refunds"]),
    ("各团队已解决工单数", "teams; agents; tickets",
     "SELECT tm.name AS team_name, COUNT(*) AS resolved_ticket_count FROM tickets t JOIN agents a ON a.id=t.assigned_agent_id JOIN teams tm ON tm.id=a.team_id WHERE t.status='resolved' GROUP BY tm.name ORDER BY resolved_ticket_count DESC LIMIT 200", ["tickets", "agents", "teams"]),
]


PREFIXES = ["请查询", "请统计", "帮我查看", "生成报表：", "我想知道", "给出", "分析", "列出", "计算", "展示"]


def main() -> None:
    rows = []
    for template_index, (label, schema, sql, tables) in enumerate(TEMPLATES):
        for prefix_index, prefix in enumerate(PREFIXES):
            question = f"{prefix}{label}"
            response = {
                "intent": "QUERY",
                "sql": sql,
                "used_tables": tables,
                "assumptions": [],
            }
            rows.append(
                {
                    "instruction": INSTRUCTION,
                    "input": f"Schema:\n{schema}\n\n问题：{question}",
                    "output": json.dumps(response, ensure_ascii=False),
                    "metadata": {
                        "id": f"smoke_train_{template_index * len(PREFIXES) + prefix_index + 1:03d}",
                        "source": "governed_smoke_template",
                    },
                }
            )
    output = ROOT / "training/datasets/llamafactory/text2sql_smoke_v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
