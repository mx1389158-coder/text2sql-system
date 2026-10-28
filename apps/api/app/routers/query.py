from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..core.config import Settings, get_settings
from ..dependencies import get_orchestrator, query_repository
from ..schemas.query import ClarifyRequest, QueryRecord, QueryRequest, QueryStatus
from ..services.orchestrator import Text2SQLOrchestrator


router = APIRouter(tags=["query"])


def verify_api_key(
    settings: Settings = Depends(get_settings), x_api_key: Optional[str] = Header(default=None)
) -> str:
    key_scopes = settings.api_key_scopes()
    if key_scopes:
        scope = key_scopes.get(x_api_key or "")
        if scope is None:
            raise HTTPException(status_code=401, detail="无效 API Key")
        return scope
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="无效 API Key")
    return "default" if settings.api_key else "anonymous"


@router.post("/query", response_model=None)
async def submit_query(
    payload: QueryRequest,
    stream: bool = Query(default=False),
    scope: str = Depends(verify_api_key),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
):
    if not stream:
        return await orchestrator.submit(
            payload.question,
            session_id=payload.session_id,
            strategy=payload.strategy,
            scope=scope,
        )

    async def events():
        yield "event: accepted\ndata: {}\n\n"
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            orchestrator.submit(
                payload.question,
                session_id=payload.session_id,
                strategy=payload.strategy,
                scope=scope,
                trace_listener=queue.put_nowait,
            )
        )
        try:
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                    body = event.model_dump(mode="json")
                    yield f"event: stage\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
            record = await task
            body = record.model_dump(mode="json")
            yield f"event: result\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
        except Exception as error:
            body = json.dumps({"detail": str(error)[:500]}, ensure_ascii=False)
            yield f"event: error\ndata: {body}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query/{query_id}/clarify", response_model=QueryRecord)
async def clarify_query(
    query_id: str,
    payload: ClarifyRequest,
    scope: str = Depends(verify_api_key),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
):
    original = query_repository.get(query_id)
    if original is None:
        raise HTTPException(status_code=404, detail="查询不存在")
    if original.status != QueryStatus.CLARIFICATION_REQUIRED:
        raise HTTPException(status_code=409, detail="该查询当前不需要澄清")
    return await orchestrator.submit(
        original.question,
        session_id=original.session_id,
        strategy=original.strategy,
        clarification_answer=payload.answer,
        existing_query_id=query_id,
        scope=scope,
    )


@router.get("/query/{query_id}", response_model=QueryRecord)
async def get_query(query_id: str, _: str = Depends(verify_api_key)):
    record = query_repository.get(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail="查询不存在")
    return record


@router.get("/queries")
async def list_queries(_: str = Depends(verify_api_key), limit: int = 50):
    return {"items": query_repository.list(max(1, min(limit, 200)))}

