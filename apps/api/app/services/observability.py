from __future__ import annotations

import logging
from typing import Any, Optional

from ..core.config import Settings
from ..schemas.query import QueryRecord, TraceEvent


logger = logging.getLogger(__name__)


class ObservabilitySink:
    """Best-effort Langfuse sink; telemetry must never break a user query."""

    def __init__(self, settings: Settings):
        self.client: Optional[Any] = None
        if not (
            settings.langfuse_host
            and settings.langfuse_public_key
            and settings.langfuse_secret_key
        ):
            return
        try:
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_host,
            )
        except (ImportError, TypeError) as error:
            logger.warning("Langfuse 未启用：%s", error)

    def emit(self, record: QueryRecord, event: TraceEvent) -> None:
        if self.client is None:
            return
        try:
            trace_id = self.client.create_trace_id(seed=record.trace_id)
            observation = self.client.start_observation(
                trace_context={"trace_id": trace_id},
                name=event.stage,
                as_type="span",
                input={"question": record.question, "strategy": record.strategy},
                metadata={
                    "query_id": record.query_id,
                    "session_id": record.session_id,
                    "status": event.status,
                    "elapsed_ms": event.elapsed_ms,
                    **event.detail,
                },
            )
            observation.update(output={"status": event.status})
            observation.end()
        except Exception as error:
            logger.warning("Langfuse trace 上报失败：%s", error)

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception as error:
                logger.warning("Langfuse flush 失败：%s", error)
