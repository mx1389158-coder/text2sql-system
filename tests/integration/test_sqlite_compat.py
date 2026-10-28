def test_postgres_interval_is_supported_in_demo(orchestrator):
    sql = "SELECT id FROM tickets WHERE created_at <= created_at + INTERVAL '7 days'"
    guarded = orchestrator.guard.validate_and_rewrite(sql)
    result = orchestrator.runner.execute(guarded.sql)
    assert result.ok


def test_postgres_epoch_extract_is_supported_in_demo(orchestrator):
    sql = "SELECT EXTRACT(EPOCH FROM (resolved_at - created_at)) AS seconds FROM tickets"
    guarded = orchestrator.guard.validate_and_rewrite(sql)
    result = orchestrator.runner.execute(guarded.sql)
    assert result.ok
