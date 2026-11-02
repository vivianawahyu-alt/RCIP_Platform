"""Correlation ID, log terstruktur, metrik in-process, dan header keamanan (TRD §12)."""
import json
import logging
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
log = logging.getLogger("rcip.request")
_lock = Lock()
_started = time.time()
_counts: dict[str, int] = defaultdict(int)
_errors: dict[str, int] = defaultdict(int)
_latency_ms: dict[str, float] = defaultdict(float)
_events: dict[str, int] = defaultdict(int)


def current_correlation_id() -> uuid.UUID:
    cid = correlation_id.get()
    try:
        return uuid.UUID(cid) if cid else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def count_event(name: str) -> None:
    with _lock:
        _events[name] += 1


def snapshot() -> dict:
    with _lock:
        routes = {k: {"requests": v, "errors": _errors.get(k, 0), "avg_ms": round(_latency_ms[k] / v, 1)}
                  for k, v in sorted(_counts.items())}
        return {"uptime_seconds": int(time.time() - _started), "routes": routes, "events": dict(_events)}


SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        try:
            cid = str(uuid.UUID(raw))
        except ValueError:
            cid = str(uuid.uuid4())
        token = correlation_id.set(cid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            route = request.scope.get("route")
            key = f"{request.method} {getattr(route, 'path', request.url.path)}"
            with _lock:
                _counts[key] += 1
                _latency_ms[key] += elapsed
                if status >= 500:
                    _errors[key] += 1
            log.info(json.dumps({"correlation_id": cid, "method": request.method, "path": request.url.path,
                                 "status": status, "ms": round(elapsed, 1)}))
            correlation_id.reset(token)
        response.headers["X-Correlation-Id"] = cid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response
