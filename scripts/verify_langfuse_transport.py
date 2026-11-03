from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from apps.api.app.core.config import Settings
from apps.api.app.schemas.query import QueryRecord, TraceEvent
from apps.api.app.services.observability import ObservabilitySink


class CaptureHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        self.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "content_type": self.headers.get("Content-Type"),
                "authorization_present": bool(self.headers.get("Authorization")),
                "body_bytes": len(payload),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_port}"
    try:
        settings = Settings(
            langfuse_host=host,
            langfuse_public_key="pk-lf-local-transport-check",
            langfuse_secret_key="sk-lf-local-transport-check",
        )
        sink = ObservabilitySink(settings)
        if sink.client is None:
            raise RuntimeError("Langfuse client was not initialized")
        record = QueryRecord(
            query_id="transport-check",
            trace_id="00000000-0000-0000-0000-000000000001",
            question="Langfuse transport verification",
        )
        sink.emit(
            record,
            TraceEvent(stage="schema_linking", status="completed", elapsed_ms=12.5, detail={}),
        )
        sink.flush()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    trace_requests = [
        request
        for request in CaptureHandler.requests
        if "trace" in str(request["path"]).lower()
        or "otel" in str(request["path"]).lower()
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if trace_requests else "failed",
        "sdk_transport_verified": bool(trace_requests),
        "live_langfuse_backend_verified": False,
        "reason_live_backend_not_started": (
            "The dedicated VM has 1 CPU and 6 GiB RAM. The official Langfuse stack requires "
            "web, worker, PostgreSQL, Redis, ClickHouse and object storage; starting it during "
            "model/database acceptance would exceed the isolated VM allocation."
        ),
        "captured_requests": CaptureHandler.requests,
    }
    output = Path("experiments/reports/langfuse-transport.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not trace_requests:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
