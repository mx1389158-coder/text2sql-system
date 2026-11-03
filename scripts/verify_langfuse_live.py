from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apps.api.app.core.config import Settings
from apps.api.app.schemas.query import QueryRecord, TraceEvent
from apps.api.app.services.observability import ObservabilitySink


def main() -> None:
    settings = Settings.from_environment()
    if not all(
        (
            settings.langfuse_host,
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
        )
    ):
        raise SystemExit("Langfuse credentials are not configured")

    sink = ObservabilitySink(settings)
    if sink.client is None:
        raise SystemExit("Langfuse client was not initialized")

    authenticated = sink.client.auth_check()
    if not authenticated:
        raise SystemExit("Langfuse authentication failed")

    verification_id = f"live-{uuid.uuid4()}"
    record = QueryRecord(
        query_id=verification_id,
        trace_id=verification_id,
        session_id="langfuse-live-verification",
        question="Langfuse Cloud live ingestion verification",
        strategy="optimized",
    )
    trace_id = sink.client.create_trace_id(seed=record.trace_id)
    sink.emit(
        record,
        TraceEvent(
            stage="cloud_ingestion_verification",
            status="completed",
            elapsed_ms=1.0,
            detail={"verification_id": verification_id, "contains_business_data": False},
        ),
    )
    sink.flush()

    observation = None
    for _ in range(15):
        response = sink.client.api.observations.get_many(trace_id=trace_id, limit=10)
        data = list(response.data)
        if data:
            observation = data[0]
            break
        time.sleep(2)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if observation is not None else "failed",
        "cloud_authentication_verified": authenticated,
        "live_langfuse_backend_verified": observation is not None,
        "trace_readback_verified": observation is not None,
        "verification_id": verification_id,
        "trace_id": trace_id,
        "observation_id": str(observation.id) if observation is not None else None,
        "observation_name": observation.name if observation is not None else None,
        "region_host": settings.langfuse_host,
    }
    output = Path("experiments/reports/langfuse-live.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sink.client.shutdown()
    if observation is None:
        raise SystemExit("Trace was not readable from Langfuse Cloud within 30 seconds")


if __name__ == "__main__":
    main()
