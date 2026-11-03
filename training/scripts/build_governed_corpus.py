from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from packages.evaluation.metrics import result_hash, result_value_hash
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
    source: str = "governed_template_verified",
    rejected_sql: str | None = None,
    error_pattern: str | None = None,
) -> dict:
    item = {
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
        "source": source,
        "review_status": "approved",
        "snapshot_id": "configured-fixed-snapshot",
    }
    if rejected_sql:
        item["rejected_sql"] = rejected_sql
    if error_pattern:
        item["error_pattern"] = error_pattern
    return item


def dated_rows(
    split: str,
    count: int,
    start: date,
    families: list[Callable[[str, str, int], dict]],
    id_prefix: str = "auto",
) -> list[dict]:
    result = []
    for index in range(count):
        cutoff = (start + timedelta(days=index % 300)).isoformat()
        family = families[index % len(families)]
        sample_id = f"biz_{split}_{id_prefix}_{index + 1:04d}"
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


def corrected_badcase_families() -> list[Callable[[str, str, int], dict]]:
    """Correct field/join patterns observed in development, without copying blind answers."""
    return [
        lambda i, d, n: row(i, f"查看{d}以来各型号最后一次固件发布时间", f"SELECT p.model_code, MAX(f.released_at) AS latest_release_at FROM firmware_versions f JOIN products p ON p.id=f.product_id WHERE f.released_at >= '{d}' GROUP BY p.model_code ORDER BY latest_release_at DESC LIMIT 200", ["firmware_versions", "products"], ["firmware_versions.product_id", "firmware_versions.released_at", "products.model_code"], "train_badcase_firmware_latest_by_model", "hard", "corrected_badcase", "SELECT f.model_code, MAX(f.released_at) FROM firmware_versions f GROUP BY f.model_code", "wrong_field_owner"),
        lambda i, d, n: row(i, f"统计{d}以来开始保修的各地区设备数", f"SELECT r.name AS region_name, COUNT(*) AS warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN customers c ON c.id=dv.customer_id JOIN regions r ON r.id=c.region_id WHERE w.starts_at >= '{d}' GROUP BY r.name ORDER BY warranty_count DESC LIMIT 200", ["warranties", "devices", "customers", "regions"], ["warranties.device_id", "warranties.starts_at", "devices.customer_id", "customers.region_id", "regions.name"], "train_badcase_warranty_region_started", "hard", "corrected_badcase", "SELECT region_id, COUNT(*) FROM warranties WHERE starts_at >= DATE '2026-01-01' GROUP BY region_id", "invented_column"),
        lambda i, d, n: row(i, f"统计{d}以来各工程师的上门服务次数", f"SELECT a.name AS agent_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id WHERE sv.started_at >= '{d}' GROUP BY a.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents"], ["service_visits.agent_id", "service_visits.started_at", "agents.name"], "train_badcase_service_visits_agent", "hard", "corrected_badcase", "SELECT team_id, COUNT(*) FROM service_visits GROUP BY team_id", "invented_column"),
        lambda i, d, n: row(i, f"统计{d}以来使用各固件版本激活的设备数", f"SELECT f.version, COUNT(*) AS device_count FROM devices dv JOIN firmware_versions f ON f.id=dv.firmware_id WHERE dv.activated_at >= '{d}' GROUP BY f.version ORDER BY device_count DESC LIMIT 200", ["devices", "firmware_versions"], ["devices.firmware_id", "devices.activated_at", "firmware_versions.version"], "train_badcase_firmware_device_adoption", "hard", "corrected_badcase", "SELECT firmware_version, COUNT(*) FROM devices GROUP BY firmware_version", "invented_column"),
        lambda i, d, n: row(i, f"统计截至{d}仍在保修的各产品分类设备数", f"SELECT pc.name AS category_name, COUNT(*) AS active_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN products p ON p.id=dv.product_id JOIN product_categories pc ON pc.id=p.category_id WHERE w.starts_at <= '{d}' AND w.ends_at >= '{d}' GROUP BY pc.name ORDER BY active_warranty_count DESC LIMIT 200", ["warranties", "devices", "products", "product_categories"], ["warranties.device_id", "warranties.starts_at", "warranties.ends_at", "devices.product_id", "products.category_id", "product_categories.name"], "train_badcase_active_warranty_category", "hard", "corrected_badcase", "SELECT category_id, COUNT(*) FROM warranties WHERE ends_at >= DATE '2026-01-01' GROUP BY category_id", "wrong_field_owner"),
        lambda i, d, n: row(i, f"统计{d}以来在职工程师完成的上门服务次数", f"SELECT a.name AS agent_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id WHERE sv.finished_at >= '{d}' AND a.status='active' GROUP BY a.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents"], ["service_visits.agent_id", "service_visits.finished_at", "agents.name", "agents.status"], "train_badcase_completed_visits_active_agent", "hard", "corrected_badcase", "SELECT a.name, COUNT(*) FROM service_visits sv JOIN agents a ON a.id=sv.ticket_id GROUP BY a.name", "wrong_join_key"),
        lambda i, d, n: row(i, f"按服务团队统计{d}之后完成的上门次数", f"SELECT tm.name AS team_name, COUNT(*) AS completed_visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id JOIN teams tm ON tm.id=a.team_id WHERE sv.finished_at >= '{d}' GROUP BY tm.name ORDER BY completed_visit_count DESC LIMIT 200", ["service_visits", "agents", "teams"], ["service_visits.agent_id", "service_visits.finished_at", "agents.team_id", "teams.name"], "train_badcase_completed_visits_team", "hard", "corrected_badcase", "SELECT tm.name, COUNT(*) FROM service_visits sv JOIN teams tm ON tm.id=sv.team_id GROUP BY tm.name", "missing_bridge_table"),
        lambda i, d, n: row(i, f"统计{d}以来各团队解决的售后工单数", f"SELECT tm.name AS team_name, COUNT(*) AS resolved_ticket_count FROM tickets t JOIN agents a ON a.id=t.assigned_agent_id JOIN teams tm ON tm.id=a.team_id WHERE t.resolved_at >= '{d}' AND t.status='resolved' GROUP BY tm.name ORDER BY resolved_ticket_count DESC LIMIT 200", ["tickets", "agents", "teams"], ["tickets.assigned_agent_id", "tickets.resolved_at", "tickets.status", "agents.team_id", "teams.name"], "train_badcase_resolved_tickets_team", "hard", "corrected_badcase", "SELECT team_id, COUNT(*) FROM tickets GROUP BY team_id", "invented_column"),
        lambda i, d, n: row(i, f"按型号统计{d}之前结束保修的设备量", f"SELECT p.model_code, COUNT(*) AS ended_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN products p ON p.id=dv.product_id WHERE w.ends_at <= '{d}' GROUP BY p.model_code ORDER BY ended_warranty_count DESC LIMIT 200", ["warranties", "devices", "products"], ["warranties.device_id", "warranties.ends_at", "devices.product_id", "products.model_code"], "train_badcase_ended_warranty_model", "hard", "corrected_badcase", "SELECT p.model_code, COUNT(*) FROM devices dv JOIN products p ON p.id=dv.product_id WHERE dv.ended_at <= DATE '2026-01-01' GROUP BY p.model_code", "wrong_field_owner"),
        lambda i, d, n: row(i, f"统计截至{d}各地区已结束的保修记录", f"SELECT r.name AS region_name, COUNT(*) AS ended_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN customers c ON c.id=dv.customer_id JOIN regions r ON r.id=c.region_id WHERE w.ends_at <= '{d}' GROUP BY r.name ORDER BY ended_warranty_count DESC LIMIT 200", ["warranties", "devices", "customers", "regions"], ["warranties.device_id", "warranties.ends_at", "devices.customer_id", "customers.region_id", "regions.name"], "train_badcase_ended_warranty_region", "hard", "corrected_badcase", "SELECT region_id, COUNT(*) FROM warranties WHERE ended_at <= DATE '2026-01-01' GROUP BY region_id", "invented_column"),
        lambda i, d, n: row(i, f"按型号汇总{d}以前发布的固件数量", f"SELECT p.model_code, COUNT(*) AS released_firmware_count FROM firmware_versions f JOIN products p ON p.id=f.product_id WHERE f.released_at <= '{d}' GROUP BY p.model_code ORDER BY released_firmware_count DESC LIMIT 200", ["firmware_versions", "products"], ["firmware_versions.product_id", "firmware_versions.released_at", "products.model_code"], "train_badcase_released_firmware_model", "hard", "corrected_badcase", "SELECT p.model_code, COUNT(*) FROM devices dv JOIN products p ON p.id=dv.product_id GROUP BY p.model_code", "wrong_fact_table"),
        lambda i, d, n: row(i, f"查看{d}以来各产品分类最新固件发布时间", f"SELECT pc.name AS category_name, MAX(f.released_at) AS latest_release_at FROM firmware_versions f JOIN products p ON p.id=f.product_id JOIN product_categories pc ON pc.id=p.category_id WHERE f.released_at >= '{d}' GROUP BY pc.name ORDER BY latest_release_at DESC LIMIT 200", ["firmware_versions", "products", "product_categories"], ["firmware_versions.product_id", "firmware_versions.released_at", "products.category_id", "product_categories.name"], "train_badcase_latest_firmware_category", "hard", "corrected_badcase", "SELECT category_id, MAX(released_at) FROM firmware_versions GROUP BY category_id", "wrong_field_owner"),
    ]


def badcase_dev_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计{d}以来各产品分类发布的固件数", f"SELECT pc.name AS category_name, COUNT(*) AS firmware_count FROM firmware_versions f JOIN products p ON p.id=f.product_id JOIN product_categories pc ON pc.id=p.category_id WHERE f.released_at >= '{d}' GROUP BY pc.name ORDER BY firmware_count DESC LIMIT 200", ["firmware_versions", "products", "product_categories"], ["firmware_versions.product_id", "firmware_versions.released_at", "products.category_id", "product_categories.name"], "dev_badcase_firmware_category", "hard"),
        lambda i, d, n: row(i, f"统计{d}到期的各地区保修记录数", f"SELECT r.name AS region_name, COUNT(*) AS warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN customers c ON c.id=dv.customer_id JOIN regions r ON r.id=c.region_id WHERE w.ends_at = '{d}' GROUP BY r.name ORDER BY warranty_count DESC LIMIT 200", ["warranties", "devices", "customers", "regions"], ["warranties.device_id", "warranties.ends_at", "devices.customer_id", "customers.region_id", "regions.name"], "dev_badcase_warranty_region_on_date", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各地区完成的上门服务次数", f"SELECT r.name AS region_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id JOIN teams tm ON tm.id=a.team_id JOIN regions r ON r.id=tm.region_id WHERE sv.finished_at >= '{d}' GROUP BY r.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents", "teams", "regions"], ["service_visits.agent_id", "service_visits.finished_at", "agents.team_id", "teams.region_id", "regions.name"], "dev_badcase_service_visits_region", "hard"),
        lambda i, d, n: row(i, f"列出{d}后各服务组完成的上门记录数", f"SELECT tm.name AS team_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id JOIN teams tm ON tm.id=a.team_id WHERE sv.finished_at >= '{d}' GROUP BY tm.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents", "teams"], ["service_visits.agent_id", "service_visits.finished_at", "agents.team_id", "teams.name"], "dev_badcase_completed_visits_team", "hard"),
        lambda i, d, n: row(i, f"列出截至{d}各设备型号已终止的保修数", f"SELECT p.model_code, COUNT(*) AS ended_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN products p ON p.id=dv.product_id WHERE w.ends_at <= '{d}' GROUP BY p.model_code ORDER BY ended_warranty_count DESC LIMIT 200", ["warranties", "devices", "products"], ["warranties.device_id", "warranties.ends_at", "devices.product_id", "products.model_code"], "dev_badcase_ended_warranty_model", "hard"),
        lambda i, d, n: row(i, f"列出截至{d}每个型号发布的固件数", f"SELECT p.model_code, COUNT(*) AS firmware_count FROM firmware_versions f JOIN products p ON p.id=f.product_id WHERE f.released_at <= '{d}' GROUP BY p.model_code ORDER BY firmware_count DESC LIMIT 200", ["firmware_versions", "products"], ["firmware_versions.product_id", "firmware_versions.released_at", "products.model_code"], "dev_badcase_released_firmware_model", "hard"),
    ]


def coverage_badcase_families() -> list[Callable[[str, str, int], dict]]:
    """Teach tables and FK paths that previously had zero SFT coverage."""
    return [
        lambda i, d, n: row(i, f"按配送城市统计{d}以来已送达的配送记录", f"SELECT ca.city, COUNT(*) AS delivered_shipment_count FROM shipments s JOIN customer_addresses ca ON ca.id=s.address_id WHERE s.delivered_at >= '{d}' AND s.status='delivered' GROUP BY ca.city ORDER BY delivered_shipment_count DESC LIMIT 200", ["shipments", "customer_addresses"], ["shipments.address_id", "shipments.delivered_at", "shipments.status", "customer_addresses.city"], "train_coverage_delivered_shipments_city", "hard", "corrected_badcase", "SELECT city, COUNT(*) FROM shipments GROUP BY city", "missing_address_join"),
        lambda i, d, n: row(i, f"统计{d}以来各配送地区发出的包裹数", f"SELECT r.name AS region_name, COUNT(*) AS shipment_count FROM shipments s JOIN customer_addresses ca ON ca.id=s.address_id JOIN regions r ON r.id=ca.region_id WHERE s.shipped_at >= '{d}' GROUP BY r.name ORDER BY shipment_count DESC LIMIT 200", ["shipments", "customer_addresses", "regions"], ["shipments.address_id", "shipments.shipped_at", "customer_addresses.region_id", "regions.name"], "train_coverage_shipments_region", "hard", "corrected_badcase", "SELECT region_id, COUNT(*) FROM shipments GROUP BY region_id", "missing_address_join"),
        lambda i, d, n: row(i, f"列出客户收货地址数量最多的前{n // 6 + 1}个地区", f"SELECT r.name AS region_name, COUNT(*) AS address_count FROM customer_addresses ca JOIN regions r ON r.id=ca.region_id GROUP BY r.name ORDER BY address_count DESC LIMIT {n // 6 + 1}", ["customer_addresses", "regions"], ["customer_addresses.region_id", "regions.name"], "train_coverage_addresses_region", "hard", "corrected_badcase", "SELECT region_id, COUNT(*) FROM customers GROUP BY region_id", "wrong_fact_table"),
        lambda i, d, n: row(i, f"汇总{d}以来各订单状态的实付金额", f"SELECT o.status AS order_status, ROUND(SUM(p.amount),2) AS paid_amount FROM payments p JOIN orders o ON o.id=p.order_id WHERE p.paid_at >= '{d}' AND p.status='paid' GROUP BY o.status ORDER BY paid_amount DESC LIMIT 200", ["payments", "orders"], ["payments.order_id", "payments.amount", "payments.paid_at", "payments.status", "orders.status"], "train_coverage_payments_order_status", "hard", "corrected_badcase", "SELECT status, SUM(total_amount) FROM orders GROUP BY status", "wrong_fact_table"),
        lambda i, d, n: row(i, f"统计{d}以来各故障分类的工单数", f"SELECT fc.category, COUNT(*) AS ticket_count FROM tickets t JOIN fault_codes fc ON fc.id=t.fault_code_id WHERE t.created_at >= '{d}' GROUP BY fc.category ORDER BY ticket_count DESC LIMIT 200", ["tickets", "fault_codes"], ["tickets.fault_code_id", "tickets.created_at", "fault_codes.category"], "train_coverage_fault_category", "hard", "corrected_badcase", "SELECT fault_category, COUNT(*) FROM tickets GROUP BY fault_category", "invented_column"),
        lambda i, d, n: row(i, f"统计{d}以来各工单事件类型数量", f"SELECT te.event_type, COUNT(*) AS event_count FROM ticket_events te WHERE te.occurred_at >= '{d}' GROUP BY te.event_type ORDER BY event_count DESC LIMIT 200", ["ticket_events"], ["ticket_events.event_type", "ticket_events.occurred_at"], "train_coverage_ticket_events", "medium", "corrected_badcase", "SELECT event_type, COUNT(*) FROM tickets GROUP BY event_type", "wrong_fact_table"),
        lambda i, d, n: row(i, f"按仓库统计单条库存不少于{n + 1}件的当前库存量", f"SELECT w.name AS warehouse_name, SUM(i.quantity) AS inventory_quantity FROM inventory i JOIN warehouses w ON w.id=i.warehouse_id WHERE i.quantity >= {n + 1} GROUP BY w.name ORDER BY inventory_quantity DESC LIMIT 200", ["inventory", "warehouses"], ["inventory.warehouse_id", "inventory.quantity", "warehouses.name"], "train_coverage_inventory_warehouse", "hard", "corrected_badcase", "SELECT warehouse_name, SUM(quantity) FROM inventory GROUP BY warehouse_name", "invented_column"),
    ]


def coverage_dev_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计{d}以来各配送地址城市的发货量", f"SELECT ca.city, COUNT(*) AS shipment_count FROM shipments s JOIN customer_addresses ca ON ca.id=s.address_id WHERE s.shipped_at >= '{d}' GROUP BY ca.city ORDER BY shipment_count DESC LIMIT 200", ["shipments", "customer_addresses"], ["shipments.address_id", "shipments.shipped_at", "customer_addresses.city"], "dev_coverage_shipments_city", "hard"),
        lambda i, d, n: row(i, f"列出{d}以来各配送地区的配送记录数", f"SELECT r.name AS region_name, COUNT(*) AS shipment_count FROM shipments s JOIN customer_addresses ca ON ca.id=s.address_id JOIN regions r ON r.id=ca.region_id WHERE s.shipped_at >= '{d}' GROUP BY r.name ORDER BY shipment_count DESC LIMIT 200", ["shipments", "customer_addresses", "regions"], ["shipments.address_id", "shipments.shipped_at", "customer_addresses.region_id", "regions.name"], "dev_coverage_shipments_region", "hard"),
        lambda i, d, n: row(i, f"查看客户地址数量最多的前{n // 6 + 1}个地区", f"SELECT r.name AS region_name, COUNT(*) AS address_count FROM customer_addresses ca JOIN regions r ON r.id=ca.region_id GROUP BY r.name ORDER BY address_count DESC LIMIT {n // 6 + 1}", ["customer_addresses", "regions"], ["customer_addresses.region_id", "regions.name"], "dev_coverage_addresses_region", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各支付状态的订单数", f"SELECT p.status, COUNT(DISTINCT p.order_id) AS order_count FROM payments p WHERE p.paid_at >= '{d}' GROUP BY p.status ORDER BY order_count DESC LIMIT 200", ["payments"], ["payments.order_id", "payments.status", "payments.paid_at"], "dev_coverage_payment_orders", "medium"),
        lambda i, d, n: row(i, f"列出{d}以来各故障代码的报修量", f"SELECT fc.code, COUNT(*) AS ticket_count FROM tickets t JOIN fault_codes fc ON fc.id=t.fault_code_id WHERE t.created_at >= '{d}' GROUP BY fc.code ORDER BY ticket_count DESC LIMIT 200", ["tickets", "fault_codes"], ["tickets.fault_code_id", "tickets.created_at", "fault_codes.code"], "dev_coverage_fault_code", "hard"),
        lambda i, d, n: row(i, f"汇总{d}以来工单状态变更事件", f"SELECT te.to_status, COUNT(*) AS transition_count FROM ticket_events te WHERE te.occurred_at >= '{d}' AND te.event_type='status_changed' GROUP BY te.to_status ORDER BY transition_count DESC LIMIT 200", ["ticket_events"], ["ticket_events.to_status", "ticket_events.occurred_at", "ticket_events.event_type"], "dev_coverage_ticket_transitions", "medium"),
        lambda i, d, n: row(i, f"按仓库所在地区汇总单条库存不少于{n + 1}件的库存量", f"SELECT r.name AS region_name, SUM(i.quantity) AS inventory_quantity FROM inventory i JOIN warehouses w ON w.id=i.warehouse_id JOIN regions r ON r.id=w.region_id WHERE i.quantity >= {n + 1} GROUP BY r.name ORDER BY inventory_quantity DESC LIMIT 200", ["inventory", "warehouses", "regions"], ["inventory.warehouse_id", "inventory.quantity", "warehouses.region_id", "regions.name"], "dev_coverage_inventory_region", "hard"),
    ]


def blind_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计截至{d}各型号到期保修设备数", f"SELECT p.model_code, COUNT(*) AS expired_warranty_count FROM warranties w JOIN devices dv ON dv.id=w.device_id JOIN products p ON p.id=dv.product_id WHERE w.ends_at <= '{d}' GROUP BY p.model_code ORDER BY expired_warranty_count DESC LIMIT 200", ["warranties", "devices", "products"], ["warranties.ends_at", "warranties.device_id", "devices.product_id", "products.model_code"], "blind_warranty_expiry", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各团队上门服务次数", f"SELECT tm.name AS team_name, COUNT(*) AS visit_count FROM service_visits sv JOIN agents a ON a.id=sv.agent_id JOIN teams tm ON tm.id=a.team_id WHERE sv.started_at >= '{d}' GROUP BY tm.name ORDER BY visit_count DESC LIMIT 200", ["service_visits", "agents", "teams"], ["service_visits.started_at", "service_visits.agent_id", "agents.team_id", "teams.name"], "blind_service_visits_team", "hard"),
        lambda i, d, n: row(i, f"统计{d}前各型号发布的固件版本数", f"SELECT p.model_code, COUNT(*) AS firmware_count FROM firmware_versions f JOIN products p ON p.id=f.product_id WHERE f.released_at <= '{d}' GROUP BY p.model_code ORDER BY firmware_count DESC LIMIT 200", ["firmware_versions", "products"], ["firmware_versions.released_at", "firmware_versions.product_id", "products.model_code"], "blind_firmware_release", "hard"),
    ]


def holdout_v2_families() -> list[Callable[[str, str, int], dict]]:
    return [
        lambda i, d, n: row(i, f"统计{d}以来各配送地区已送达的订单数", f"SELECT r.name AS region_name, COUNT(*) AS delivered_order_count FROM shipments s JOIN customer_addresses ca ON ca.id=s.address_id JOIN regions r ON r.id=ca.region_id WHERE s.delivered_at >= '{d}' AND s.status='delivered' GROUP BY r.name ORDER BY delivered_order_count DESC LIMIT 200", ["shipments", "customer_addresses", "regions"], ["shipments.address_id", "shipments.delivered_at", "shipments.status", "customer_addresses.region_id", "regions.name"], "holdout_v2_delivered_orders_region", "hard"),
        lambda i, d, n: row(i, f"汇总{d}以来各产品分类获批的退款金额", f"SELECT pc.name AS category_name, ROUND(SUM(r.amount),2) AS approved_refund_amount FROM refunds r JOIN order_items oi ON oi.id=r.order_item_id JOIN products p ON p.id=oi.product_id JOIN product_categories pc ON pc.id=p.category_id WHERE r.created_at >= '{d}' AND r.status='approved' GROUP BY pc.name ORDER BY approved_refund_amount DESC LIMIT 200", ["refunds", "order_items", "products", "product_categories"], ["refunds.order_item_id", "refunds.amount", "refunds.created_at", "refunds.status", "order_items.product_id", "products.category_id", "product_categories.name"], "holdout_v2_refunds_category", "hard"),
        lambda i, d, n: row(i, f"统计{d}以来各地区失败的设备升级次数", f"SELECT r.name AS region_name, COUNT(*) AS failed_upgrade_count FROM device_upgrades du JOIN devices dv ON dv.id=du.device_id JOIN customers c ON c.id=dv.customer_id JOIN regions r ON r.id=c.region_id WHERE du.upgraded_at >= '{d}' AND du.status='failed' GROUP BY r.name ORDER BY failed_upgrade_count DESC LIMIT 200", ["device_upgrades", "devices", "customers", "regions"], ["device_upgrades.device_id", "device_upgrades.upgraded_at", "device_upgrades.status", "devices.customer_id", "customers.region_id", "regions.name"], "holdout_v2_failed_upgrades_region", "hard"),
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
        item["expected_value_hash"] = result_value_hash(
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
        additions = []
        if split == "train":
            additions = dated_rows(
                split,
                900,
                date(2024, 7, 1),
                corrected_badcase_families(),
                id_prefix="badcase",
            )
            additions += dated_rows(
                split,
                700,
                date(2024, 10, 1),
                coverage_badcase_families(),
                id_prefix="coverage",
            )
        elif split == "dev":
            additions = dated_rows(
                split,
                180,
                date(2025, 7, 1),
                badcase_dev_families(),
                id_prefix="badcase",
            )
            additions += dated_rows(
                split,
                140,
                date(2025, 10, 1),
                coverage_dev_families(),
                id_prefix="coverage",
            )
        rows = manual + generated + additions
        write_split(split, rows, runner)
        print(f"{split}: {len(rows)}")
    holdout_v2 = dated_rows(
        "holdout_v2",
        300,
        date(2026, 7, 1),
        holdout_v2_families(),
    )
    write_split("holdout_v2", holdout_v2, runner)
    print(f"holdout_v2: {len(holdout_v2)}")


if __name__ == "__main__":
    main()
