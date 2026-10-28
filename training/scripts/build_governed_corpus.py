from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from packages.evaluation.metrics import result_hash
from packages.execution.runner import PostgresRunner, SQLiteRunner


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "training/datasets/raw"


def existing_manual(split: str) -> list[dict]:
    path = RAW / f"{split}.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if row.get("source") == "manual_verified"]


def row(
    sample_id: str,
    question: str,
    sql: str,
    tables: list[str],
    columns: list[str],
    template_group: str,
    difficulty: str = "medium",
) -> dict:
    return {
        "id": sample_id,
        "question": question,
        "dialect": "postgres",
        "schema_context": "; ".join(tables),
        "clarification": None,
        "sql": sql,
        "tables": tables,
        "columns": columns,
        "difficulty": difficulty,
        "template_group": template_group,
        "source": "governed_template_verified",
        "review_status": "approved",
        "snapshot_id": "configured-fixed-snapshot",
    }


def dated_rows(
    split: str,
    count: int,
    start: date,
    families: list[Callable[[str, str, int], dict]],
) -> list[dict]:
    result = []
    for index in range(count):
        cutoff = (start + timedelta(days=index % 300)).isoformat()
        family = families[index % len(families)]
        sample_id = f"biz_{split}_auto_{index + 1:04d}"
        result.append(family(sample_id, cutoff, index))
    return result


def train_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计{d}以来各状态订单数", f"SELECT status, COUNT(*) AS order_count FROM orders WHERE ordered_at >= '{d}' GROUP BY status ORDER BY order_count DESC LIMIT 200", ["orders"], ["orders.status", "orders.ordered_at"], "train_orders_status_since"),
        lambda i, d, n: row(i, f"汇总{d}以来各地区订单金额", f"SELECT r.name AS region_name, ROUND(SUM(o.total_amount),2) AS revenue FROM orders o JOIN customers c ON c.id=o.customer_id JOIN regions r ON r.id=c.region_id WHERE o.ordered_at >= '{d}' AND o.status IN ('paid','completed') GROUP BY r.name ORDER BY revenue DESC LIMIT 200", ["orders", "customers", "regions"], ["orders.total_amount", "orders.ordered_at", "orders.status", "customers.region_id", "regions.name"], "train_revenue_region_since", "hard"),
        lambda i, d, n: row(i, f"查看{d}以来各型号销售件数", f"SELECT p.model_code, SUM(oi.quantity) AS sold_units FROM orders o JOIN order_items oi ON oi.order_id=o.id JOIN products p ON p.id=oi.product_id WHERE o.ordered_at >= '{d}' AND o.status='completed' GROUP BY p.model_code ORDER BY sold_units DESC LIMIT 200", ["orders", "order_items", "products"], ["orders.ordered_at", "orders.status", "order_items.quantity", "products.model_code"], "train_units_model_since", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各地区新增客户", f"SELECT r.name AS region_name, COUNT(*) AS customer_count FROM customers c JOIN regions r ON r.id=c.region_id WHERE c.registered_at >= '{d}' GROUP BY r.name ORDER BY customer_count DESC LIMIT 200", ["customers", "regions"], ["customers.registered_at", "customers.region_id", "regions.name"], "train_customers_region_since"),
        lambda i, d, n: row(i, f"统计{d}以来各型号激活设备数", f"SELECT p.model_code, COUNT(*) AS device_count FROM devices d JOIN products p ON p.id=d.product_id WHERE d.activated_at >= '{d}' GROUP BY p.model_code ORDER BY device_count DESC LIMIT 200", ["devices", "products"], ["devices.activated_at", "devices.product_id", "products.model_code"], "train_devices_model_since"),
        lambda i, d, n: row(i, f"统计{d}以来不同状态的工单数量", f"SELECT status, COUNT(*) AS ticket_count FROM tickets WHERE created_at >= '{d}' GROUP BY status ORDER BY ticket_count DESC LIMIT 200", ["tickets"], ["tickets.status", "tickets.created_at"], "train_tickets_status_since"),
        lambda i, d, n: row(i, f"统计{d}以来各退款类型申请数", f"SELECT refund_type, COUNT(*) AS refund_count FROM refunds WHERE created_at >= '{d}' GROUP BY refund_type ORDER BY refund_count DESC LIMIT 200", ["refunds"], ["refunds.refund_type", "refunds.created_at"], "train_refunds_type_since"),
        lambda i, d, n: row(i, f"统计{d}以来设备升级状态分布", f"SELECT status, COUNT(*) AS upgrade_count FROM device_upgrades WHERE upgraded_at >= '{d}' GROUP BY status ORDER BY upgrade_count DESC LIMIT 200", ["device_upgrades"], ["device_upgrades.status", "device_upgrades.upgraded_at"], "train_upgrades_status_since"),
        lambda i, d, n: row(i, f"列出库存不少于{n % 200 + 1}件的产品型号", f"SELECT p.model_code, SUM(i.quantity) AS inventory_quantity FROM inventory i JOIN products p ON p.id=i.product_id GROUP BY p.model_code HAVING SUM(i.quantity) >= {n % 200 + 1} ORDER BY inventory_quantity DESC LIMIT 200", ["inventory", "products"], ["inventory.quantity", "inventory.product_id", "products.model_code"], "train_inventory_threshold"),
        lambda i, d, n: row(i, f"统计{d}以来各型号平均满意度", f"SELECT p.model_code, ROUND(AVG(s.score),2) AS avg_score, COUNT(*) AS survey_count FROM satisfaction_surveys s JOIN tickets t ON t.id=s.ticket_id JOIN devices dv ON dv.id=t.device_id JOIN products p ON p.id=dv.product_id WHERE s.submitted_at >= '{d}' GROUP BY p.model_code ORDER BY avg_score DESC LIMIT 200", ["satisfaction_surveys", "tickets", "devices", "products"], ["satisfaction_surveys.score", "satisfaction_surveys.submitted_at", "tickets.device_id", "devices.product_id", "products.model_code"], "train_satisfaction_model_since", "hard"),
    ]


def dev_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计{d}以来各支付状态的金额", f"SELECT status, ROUND(SUM(amount),2) AS payment_amount FROM payments WHERE paid_at >= '{d}' GROUP BY status ORDER BY payment_amount DESC LIMIT 200", ["payments"], ["payments.status", "payments.amount", "payments.paid_at"], "dev_payments_status_since"),
        lambda i, d, n: row(i, f"统计{d}以来各配送状态订单数", f"SELECT status, COUNT(*) AS shipment_count FROM shipments WHERE shipped_at >= '{d}' GROUP BY status ORDER BY shipment_count DESC LIMIT 200", ["shipments"], ["shipments.status", "shipments.shipped_at"], "dev_shipments_status_since"),
        lambda i, d, n: row(i, f"统计{d}以来工单事件类型分布", f"SELECT event_type, COUNT(*) AS event_count FROM ticket_events WHERE occurred_at >= '{d}' GROUP BY event_type ORDER BY event_count DESC LIMIT 200", ["ticket_events"], ["ticket_events.event_type", "ticket_events.occurred_at"], "dev_ticket_events_since"),
    ]


def blind_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计截至{d}各型号到期保修设备数", f"SELECT p.model_code, COUNT(*) AS expired_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN products p ON p.id=dv.product_id WHERE w.ends_at <= '{d}' GROUP BY p.model_code ORDER BY expired_warranty_count DESC LIMIT 200", ["warranties", "devices", "products"], ["warranties.ends_at", "warranties.device_id", "devices.product_id", "products.model_code"], "blind_warranty_expiry", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各团队上门服务次数", f"SELECT tm.name AS team_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id JOIN teams tm ON tm.id=a.team_id WHERE sv.started_at >= '{d}' GROUP BY tm.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents", "teams"], ["service_visits.started_at", "service_visits.agent_id", "agents.team_id", "teams.name"], "blind_service_visits_team", "hard"),
        lambda i, d, n: row(i, f"统计{d}前各型号发布的固件版本数", f"SELECT p.model_code, COUNT(*) AS firmware_count FROM firmware_versions f JOIN products p ON p.id=f.product_id WHERE f.released_at <= '{d}' GROUP BY p.model_code ORDER BY firmware_count DESC LIMIT 200", ["firmware_versions", "products"], ["firmware_versions.released_at", "firmware_versions.product_id", "products.model_code"], "blind_firmware_release", "hard"),
    ]


def write_split(split: str, rows: list[dict], runner) -> None:
    for item in rows:
        item.setdefault("review_status", "approved")
        item.setdefault("snapshot_id", "configured-fixed-snapshot")
        execution = runner.execute(item["sql"])
        if not execution.ok:
            message = execution.error.safe_message if execution.error else "unknown"
            raise ValueError(f"{item['id']} failed: {message}")
        item["expected_result_hash"] = result_hash(
            execution.rows, bool(item.get("order_sensitive", False))
        )
    path = RAW / f"{split}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for item in rows:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build execution-verified governed business corpus")
    parser.add_argument("--database-url", default="sqlite:///data/snapshots/demo.db")
    args = parser.parse_args()
    runner = (
        SQLiteRunner(args.database_url[len("sqlite:///") :], max_rows=10000)
        if args.database_url.startswith("sqlite:///")
        else PostgresRunner(args.database_url, max_rows=10000, statement_timeout_ms=30000)
    )
    plans = {
        "train": (2500, date(2024, 1, 1), train_families()),
        "dev": (300, date(2025, 1, 1), dev_families()),
        "blind": (300, date(2026, 1, 1), blind_families()),
    }
    for split, (target, start, families) in plans.items():
        manual = existing_manual(split)
        generated = dated_rows(split, target - len(manual), start, families)
        rows = manual + generated
        write_split(split, rows, runner)
        print(f"{split}: {len(rows)}")


if __name__ == "__main__":
    main()
