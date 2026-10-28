from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings


router = APIRouter(tags=["system"])


@router.get("/system")
async def system_info(settings: Settings = Depends(get_settings)):
    """Expose non-secret runtime facts needed by the same-origin workbench."""
    is_demo = settings.llm_provider == "demo"
    database_engine = settings.database_url.split(":", 1)[0]
    return {
        "environment": settings.env,
        "mode": "demo" if is_demo else "production",
        "provider": settings.llm_provider,
        "model": "demo" if is_demo else settings.llm_model,
        "database_engine": database_engine,
        "evaluation_dataset": "data/processed/smoke.jsonl",
        "security": {
            "ast_guard": True,
            "read_only": True,
            "row_limit": settings.max_rows,
        },
    }
