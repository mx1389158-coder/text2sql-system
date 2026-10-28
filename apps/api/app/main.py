from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .routers import catalog, evals, feedback, models, query
from .services.limits import SafetyLimitsMiddleware


app = FastAPI(
    title="星云智家智能问数 API",
    version="0.1.0",
    description="Schema Linking、只读 SQL 执行、反馈修正与可复现实验 API",
)
_settings = get_settings()
app.add_middleware(
    SafetyLimitsMiddleware,
    requests_per_window=_settings.rate_limit_requests,
    window_seconds=_settings.rate_limit_window_seconds,
    max_concurrent=_settings.max_concurrent_requests,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for api_router in (query.router, feedback.router, catalog.router, evals.router, models.router):
    app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def recover_evaluation_jobs() -> None:
    await evals.recover_jobs()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "nebula-text2sql"}

