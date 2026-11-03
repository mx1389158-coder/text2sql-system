# Badcase 分类报告

生成时间：`2026-11-03T05:51:59.065888+00:00`。主要分析 A40 控制组在 81 条、17 个模板族切片上的错误。

## 错误类型

| 类型 | 数量 |
| --- | ---: |
| wrong_field_or_grouping | 18 |
| other_execution_or_result_mismatch | 16 |

## 模板族准确率

| 模板族 | 正确 | 总数 | 准确率 |
| --- | ---: | ---: | ---: |
| dev_badcase_completed_visits_team | 5 | 5 | 100.00% |
| dev_badcase_ended_warranty_model | 5 | 5 | 100.00% |
| dev_badcase_firmware_category | 2 | 5 | 40.00% |
| dev_badcase_released_firmware_model | 5 | 5 | 100.00% |
| dev_badcase_service_visits_region | 0 | 5 | 0.00% |
| dev_badcase_warranty_region_on_date | 5 | 5 | 100.00% |
| dev_coverage_addresses_region | 0 | 5 | 0.00% |
| dev_coverage_fault_code | 5 | 5 | 100.00% |
| dev_coverage_inventory_region | 5 | 5 | 100.00% |
| dev_coverage_payment_orders | 5 | 5 | 100.00% |
| dev_coverage_shipments_city | 0 | 5 | 0.00% |
| dev_coverage_shipments_region | 5 | 5 | 100.00% |
| dev_coverage_ticket_transitions | 0 | 5 | 0.00% |
| dev_payments_status_since | 5 | 5 | 100.00% |
| dev_shipments_status_since | 0 | 5 | 0.00% |
| dev_ticket_events_since | 0 | 5 | 0.00% |
| satisfaction_by_model | 0 | 1 | 0.00% |

## 优先处理建议

1. `wrong_field_or_grouping`：继续补字段归属负例和 GROUP BY 纠错训练样本。
2. `semantic_rejection`：检查候选阈值、Schema 字段召回和唯一 FK 路径归一化。
3. `other_execution_or_result_mismatch`：按模板族核对状态值、时间字段与聚合口径。
4. `infrastructure_connection`：不得计入模型能力结论，恢复数据库后整组重跑。

完整逐样本记录保存在 `experiments/reports/final-summary.json`。
