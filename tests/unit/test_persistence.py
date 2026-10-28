from apps.api.app.repositories import JobRepository, QueryRepository
from apps.api.app.schemas.query import QueryRecord


def test_query_repository_round_trip(tmp_path):
    path = tmp_path / "state.db"
    first = QueryRepository(path)
    first.save(QueryRecord(query_id="q1", trace_id="t1", question="测试"))
    second = QueryRepository(path)
    assert second.get("q1").question == "测试"
    assert second.list()[0].query_id == "q1"


def test_job_repository_recovers_pending_jobs(tmp_path):
    repository = JobRepository(tmp_path / "state.db")
    repository.create("job-1", {"dataset_path": "x", "model": "demo"})
    assert repository.recoverable()[0]["job_id"] == "job-1"
    repository.update("job-1", "completed", result={"total": 1})
    assert repository.get("job-1")["summary"]["total"] == 1
    assert repository.recoverable() == []
