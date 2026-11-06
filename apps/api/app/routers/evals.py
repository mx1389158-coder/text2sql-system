from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Set

from fastapi import APIRouter, Depends, HTTPException

from packages.evaluation.runner import EvaluationRunner

from ..core.config import Settings, get_settings
from ..dependencies import get_orchestrator, job_repository
from ..schemas.query import EvalRunRequest
from ..services.orchestrator import Text2SQLOrchestrator
from .query import verify_api_key


router = APIRouter(tags=["evaluation"])
_tasks: Set[asyncio.Task] = set()
EVALUATION_SCOPE = "evaluation"


def require_evaluation_scope(scope: str = Depends(verify_api_key)) -> str:
    if scope != EVALUATION_SCOPE:
        raise HTTPException(status_code=403, detail="evaluation scope required")
    return scope


async def _run(
    job_id: str,
    scope: str,
    payload: EvalRunRequest,
    orchestrator: Text2SQLOrchestrator,
) -> None:
    job_repository.update(job_id, scope, "running")
    try:
        runner = EvaluationRunner(orchestrator)
        summary = await runner.run(payload.dataset_path, strategy=payload.strategy)
        output = Path("experiments/reports") / f"{job_id}.json"
        runner.write(summary, output)
        result = asdict(summary)
        result["report"] = str(output)
        result["model"] = payload.model
        result["strategy"] = payload.strategy
        result["experiment_id"] = payload.experiment_id
        job_repository.update(job_id, scope, "completed", result=result)
    except Exception as error:
        job_repository.update(job_id, scope, "failed", error=str(error)[:500])


def _schedule(
    job_id: str,
    scope: str,
    payload: EvalRunRequest,
    orchestrator: Text2SQLOrchestrator,
) -> None:
    task = asyncio.create_task(_run(job_id, scope, payload, orchestrator))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def recover_jobs() -> None:
    orchestrator = get_orchestrator()
    settings = get_settings()
    for job in job_repository.recoverable(
        EVALUATION_SCOPE, limit=settings.max_active_evaluation_jobs
    ):
        job_repository.update(job["job_id"], EVALUATION_SCOPE, "queued")
        _schedule(
            job["job_id"],
            EVALUATION_SCOPE,
            EvalRunRequest(**job["payload"]),
            orchestrator,
        )


@router.post("/evals/run", status_code=202)
async def start_eval(
    payload: EvalRunRequest,
    scope: str = Depends(require_evaluation_scope),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
):
    root = settings.evaluation_allowed_root.resolve()
    dataset = Path(payload.dataset_path).resolve()
    if root != dataset and root not in dataset.parents:
        raise HTTPException(status_code=403, detail="评测数据集必须位于允许的数据目录内")
    if not dataset.exists() or not dataset.is_file():
        raise HTTPException(status_code=404, detail="评测数据集不存在")
    configured_model = "demo" if settings.llm_provider == "demo" else settings.llm_model
    if payload.model not in {configured_model, "demo", "demo-rules"}:
        raise HTTPException(status_code=422, detail="请求的模型与当前 API 实例不匹配")
    payload.dataset_path = str(dataset)
    job_id = str(uuid.uuid4())
    job = job_repository.create(
        job_id,
        scope,
        payload.model_dump(mode="json"),
        max_active_jobs=settings.max_active_evaluation_jobs,
    )
    if job is None:
        raise HTTPException(
            status_code=429,
            detail="maximum active evaluation jobs reached",
            headers={"Retry-After": "5"},
        )
    _schedule(job_id, scope, payload, orchestrator)
    return {"job_id": job_id, "status": "queued"}


@router.get("/evals/{job_id}")
async def get_eval(job_id: str, scope: str = Depends(require_evaluation_scope)):
    job = job_repository.get(job_id, scope)
    if job is None:
        raise HTTPException(status_code=404, detail="评测任务不存在")
    return job


@router.get("/evals")
async def list_evals(scope: str = Depends(require_evaluation_scope), limit: int = 50):
    return {"jobs": job_repository.list(scope, max(1, min(limit, 200)))}

