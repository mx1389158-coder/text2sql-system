from packages.generation.governed_metrics import GovernedMetricCompiler


def test_compiles_only_reviewed_clarification_options(guard):
    compiler = GovernedMetricCompiler()
    candidate = compiler.compile(
        "各型号的退换货率是多少？",
        "return_exchange_rate",
        "按申请时间，仅退货/换货；统计全部历史",
    )
    assert candidate is not None
    assert candidate.provider == "governed-metric-compiler"
    assert candidate.provider_calls == 0
    assert "approved_returns" in candidate.sql
    guard.validate_and_rewrite(candidate.sql)
    assert compiler.compile(
        "各型号的退换货率是多少？",
        "return_exchange_rate",
        "包含仅退款",
    ) is None


def test_all_resolution_topics_compile_to_guarded_sql(guard):
    compiler = GovernedMetricCompiler()
    rows = [
        ("销售额是多少？", "revenue", "按成功支付金额和支付时间；统计全部历史"),
        ("有效订单是多少？", "valid_order", "按下单时间；统计全部历史"),
        ("活跃设备是多少？", "active_device", "近30天有升级或报修；截至2026-10-01"),
        ("故障率是多少？", "failure_rate", "故障设备数/激活设备数；统计全部历史"),
        ("解决时长是多少？", "resolution_duration", "创建到解决，仅已解决工单；统计全部历史"),
        ("满意度是多少？", "satisfaction", "全部有效评价并返回评价数"),
        ("复购率是多少？", "repurchase_rate", "全部历史按客户"),
        ("升级成功率是多少？", "upgrade_success_rate", "全部历史按升级次数"),
        ("各型号的库存是多少？", "inventory_snapshot", "当前快照按型号汇总"),
    ]
    for question, key, answer in rows:
        candidate = compiler.compile(question, key, answer)
        assert candidate is not None, key
        guard.validate_and_rewrite(candidate.sql)
