from __future__ import annotations

import re
from typing import Optional

from .models import GeneratedCandidate


class GovernedMetricCompiler:
    """Compile an explicitly selected, versioned business definition into reviewed SQL."""

    _ANSWER_PREFIXES = {
        "return_exchange_rate": ("按申请时间，仅退货/换货",),
        "revenue": ("按成功支付金额和支付时间",),
        "valid_order": ("按下单时间",),
        "active_device": ("近30天有升级或报修",),
        "failure_rate": ("故障设备数/激活设备数",),
        "resolution_duration": ("创建到解决，仅已解决工单",),
        "satisfaction": ("全部有效评价并返回评价数",),
        "repurchase_rate": ("全部历史按客户",),
        "upgrade_success_rate": ("全部历史按升级次数",),
        "inventory_snapshot": ("当前快照按型号汇总",),
    }

    def compile(
        self,
        question: str,
        ambiguity_key: str,
        clarification_answer: str,
    ) -> Optional[GeneratedCandidate]:
        prefixes = self._ANSWER_PREFIXES.get(ambiguity_key, ())
        if not prefixes or not any(clarification_answer.startswith(item) for item in prefixes):
            return None
        sql = self._sql(question, ambiguity_key, clarification_answer)
        if sql is None:
            return None
        return GeneratedCandidate(
            sql=sql,
            used_tables=self._tables(ambiguity_key),
            assumptions=[
                f"governed metric definition: {ambiguity_key}@1.0",
                f"user-confirmed definition: {clarification_answer}",
            ],
            raw_response="governed metric compiler",
            provider="governed-metric-compiler",
            provider_calls=0,
        )

    @staticmethod
    def _tables(key: str) -> list[str]:
        return {
            "return_exchange_rate": ["orders", "order_items", "refunds", "products"],
            "revenue": ["payments"],
            "valid_order": ["orders"],
            "active_device": ["device_upgrades", "tickets"],
            "failure_rate": ["devices", "tickets"],
            "resolution_duration": ["tickets"],
            "satisfaction": ["satisfaction_surveys"],
            "repurchase_rate": ["orders"],
            "upgrade_success_rate": ["device_upgrades"],
            "inventory_snapshot": ["inventory", "products"],
        }[key]

    def _sql(self, question: str, key: str, answer: str) -> Optional[str]:
        by_model = any(marker in question for marker in ("型号", "产品"))
        if key == "return_exchange_rate":
            if by_model:
                return (
                    "WITH valid_items AS (SELECT oi.id, oi.product_id FROM order_items oi "
                    "JOIN orders o ON o.id=oi.order_id WHERE o.status IN ('paid','completed')), "
                    "approved_returns AS (SELECT DISTINCT r.order_item_id FROM refunds r "
                    "WHERE r.status='approved' AND r.refund_type IN ('return','exchange')) "
                    "SELECT p.model_code, ROUND(COUNT(ar.order_item_id)::numeric / "
                    "NULLIF(COUNT(vi.id),0),4) AS return_exchange_rate FROM valid_items vi "
                    "JOIN products p ON p.id=vi.product_id LEFT JOIN approved_returns ar "
                    "ON ar.order_item_id=vi.id GROUP BY p.model_code "
                    "ORDER BY return_exchange_rate ASC, p.model_code LIMIT 200"
                )
            return (
                "WITH valid_items AS (SELECT oi.id FROM order_items oi JOIN orders o "
                "ON o.id=oi.order_id WHERE o.status IN ('paid','completed')), "
                "approved_returns AS (SELECT DISTINCT r.order_item_id FROM refunds r "
                "WHERE r.status='approved' AND r.refund_type IN ('return','exchange')) "
                "SELECT ROUND(COUNT(ar.order_item_id)::numeric / NULLIF(COUNT(vi.id),0),4) "
                "AS return_exchange_rate FROM valid_items vi LEFT JOIN approved_returns ar "
                "ON ar.order_item_id=vi.id"
            )
        if key == "revenue":
            return (
                "SELECT ROUND(SUM(amount),2) AS revenue FROM payments "
                "WHERE status='succeeded'"
            )
        if key == "valid_order":
            return (
                "SELECT COUNT(*) AS valid_order_count FROM orders "
                "WHERE status IN ('paid','completed')"
            )
        if key == "active_device":
            match = re.search(r"截至\s*(\d{4}-\d{2}-\d{2})", answer)
            if match:
                end_date = match.group(1)
                return (
                    "SELECT COUNT(DISTINCT device_id) AS active_device_count FROM ("
                    f"SELECT du.device_id FROM device_upgrades du WHERE du.upgraded_at >= "
                    f"TIMESTAMP '{end_date}' - INTERVAL '30 days' AND du.upgraded_at < "
                    f"TIMESTAMP '{end_date}' + INTERVAL '1 day' UNION SELECT t.device_id "
                    f"FROM tickets t WHERE t.created_at >= TIMESTAMP '{end_date}' - "
                    f"INTERVAL '30 days' AND t.created_at < TIMESTAMP '{end_date}' + "
                    "INTERVAL '1 day') activity"
                )
            return (
                "SELECT COUNT(DISTINCT device_id) AS active_device_count FROM ("
                "SELECT du.device_id FROM device_upgrades du WHERE du.upgraded_at >= "
                "CURRENT_DATE - INTERVAL '30 days' UNION SELECT t.device_id FROM tickets t "
                "WHERE t.created_at >= CURRENT_DATE - INTERVAL '30 days') activity"
            )
        if key == "failure_rate":
            return (
                "SELECT ROUND(COUNT(DISTINCT t.device_id)::numeric / "
                "NULLIF(COUNT(DISTINCT d.id),0),4) AS failure_rate FROM devices d "
                "LEFT JOIN tickets t ON t.device_id=d.id"
            )
        if key == "resolution_duration":
            return (
                "SELECT ROUND(AVG(EXTRACT(EPOCH FROM (resolved_at-created_at))/3600.0),2) "
                "AS avg_resolution_hours FROM tickets WHERE status='resolved' "
                "AND resolved_at IS NOT NULL"
            )
        if key == "satisfaction":
            return (
                "SELECT ROUND(AVG(score),2) AS avg_satisfaction, COUNT(*) AS survey_count "
                "FROM satisfaction_surveys WHERE score IS NOT NULL"
            )
        if key == "repurchase_rate":
            return (
                "WITH customer_orders AS (SELECT customer_id, COUNT(*) AS order_count "
                "FROM orders WHERE status IN ('paid','completed') GROUP BY customer_id) "
                "SELECT ROUND(COUNT(*) FILTER (WHERE order_count >= 2)::numeric / "
                "NULLIF(COUNT(*),0),4) AS repurchase_rate FROM customer_orders"
            )
        if key == "upgrade_success_rate":
            return (
                "SELECT ROUND(COUNT(*) FILTER (WHERE status='success')::numeric / "
                "NULLIF(COUNT(*),0),4) AS upgrade_success_rate FROM device_upgrades"
            )
        if key == "inventory_snapshot":
            return (
                "SELECT p.model_code, SUM(i.quantity) AS inventory_quantity FROM inventory i "
                "JOIN products p ON p.id=i.product_id GROUP BY p.model_code "
                "ORDER BY inventory_quantity DESC, p.model_code LIMIT 200"
            )
        return None
