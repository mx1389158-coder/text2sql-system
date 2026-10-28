from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class SafetyLimitsMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_window: int,
        window_seconds: int,
        max_concurrent: int,
    ):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.history: Dict[str, Deque[float]] = defaultdict(deque)
        self.lock = threading.RLock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("x-api-key") or (
            request.client.host if request.client else "unknown"
        )
        now = time.monotonic()
        with self.lock:
            history = self.history[key]
            while history and history[0] <= now - self.window_seconds:
                history.popleft()
            if len(history) >= self.requests_per_window:
                retry_after = max(1, int(self.window_seconds - (now - history[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后重试"},
                    headers={"Retry-After": str(retry_after)},
                )
            history.append(now)
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=0.05)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=429, content={"detail": "系统并发已达安全上限"})
        try:
            return await call_next(request)
        finally:
            self.semaphore.release()
