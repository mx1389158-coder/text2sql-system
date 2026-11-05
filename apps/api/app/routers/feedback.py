from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import feedback_repository, get_orchestrator, query_repository
from ..schemas.query import FeedbackRequest
from ..services.orchestrator import Text2SQLOrchestrator
from .query import verify_api_key


router = APIRouter(tags=["feedback"])


@router.get("/feedback")
async def list_feedback(scope: str = Depends(verify_api_key), limit: int = 100):
    return {"items": feedback_repository.list(scope, max(1, min(limit, 500)))}


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    scope: str = Depends(verify_api_key),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
):
    query = query_repository.get(payload.query_id, scope)
    if query is None:
        raise HTTPException(status_code=404, detail="查询不存在")
    if payload.corrected_sql:
        try:
            orchestrator.guard.validate_and_rewrite(payload.corrected_sql)
        except Exception as error:
            raise HTTPException(
                status_code=422, detail=f"修正 SQL 未通过安全检查：{error}"
            ) from error
    feedback_repository.append(payload, query)
    return {"accepted": True, "training_status": "candidate_only"}

