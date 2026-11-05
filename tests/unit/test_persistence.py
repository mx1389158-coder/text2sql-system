from apps.api.app.repositories import JobRepository, QueryRepository
from apps.api.app.schemas.query import QueryRecord


def test_query_repository_round_trip(tmp_path):
    path = tmp_path / "state.db"
    first = QueryRepository(path)
    first.save(
        QueryRecord(query_id="q1", trace_id="t1", question="测试", scope="analyst")
    )
    second = QueryRepository(path)
    assert second.get("q1", "analyst").question == "测试"
    assert second.get("q1", "attacker") is None
    assert second.list("analyst")[0].query_id == "q1"
    assert second.list("attacker") == []


def test_query_repository_migrates_legacy_records_fail_closed(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    record = QueryRecord(query_id="legacy", trace_id="trace", question="旧记录")
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE query_records (
                query_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO query_records VALUES (?, ?, ?)",
            ("legacy", record.model_dump_json(), record.updated_at.isoformat()),
        )

    repository = QueryRepository(path)

    assert repository.get("legacy", "default") is None
    assert repository.list("default") == []


def test_query_repository_rejects_scope_ownership_change(tmp_path):
    repository = QueryRepository(tmp_path / "state.db")
    repository.save(
        QueryRecord(query_id="q1", trace_id="t1", question="测试", scope="analyst")
    )

    try:
        repository.save(
            QueryRecord(query_id="q1", trace_id="t2", question="覆盖", scope="admin")
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("query ownership must be immutable")


def test_job_repository_recovers_pending_jobs(tmp_path):
    repository = JobRepository(tmp_path / "state.db")
    repository.create("job-1", {"dataset_path": "x", "model": "demo"})
    assert repository.recoverable()[0]["job_id"] == "job-1"
    repository.update("job-1", "completed", result={"total": 1})
    assert repository.get("job-1")["summary"]["total"] == 1
    assert repository.recoverable() == []
