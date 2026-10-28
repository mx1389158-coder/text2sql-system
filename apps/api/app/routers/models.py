from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from .query import verify_api_key


router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models(_: str = Depends(verify_api_key)):
    path = Path("training/model_registry.json")
    if not path.exists():
        return {"models": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

