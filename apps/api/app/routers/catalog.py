from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_orchestrator
from ..services.orchestrator import Text2SQLOrchestrator
from .query import verify_api_key


router = APIRouter(tags=["catalog"])


@router.get("/schema")
async def get_schema(
    _: str = Depends(verify_api_key),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
):
    return orchestrator.catalog.to_dict()

