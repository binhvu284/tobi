"""HTTP compatibility projection for Projects and Office route groups."""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.runtime.surface_adapter import SurfaceRuntimeAdapter


_SURFACE_PREFIXES = (("/api/pm", "projects"), ("/api/office", "office"))
_IDENTIFIER = re.compile(r"^(?:\d+|[0-9a-fA-F-]{16,})$")


def _surface(path: str) -> str | None:
    return next((
        surface
        for prefix, surface in _SURFACE_PREFIXES
        if path == prefix or path.startswith(f"{prefix}/")
    ), None)


def _operation(method: str, path: str) -> str:
    parts = ["ref" if _IDENTIFIER.fullmatch(part) else part for part in path.split("/") if part]
    return ".".join([method.lower(), *parts])[:160]


class RuntimeSurfaceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        surface = _surface(request.url.path)
        if surface is None:
            return await call_next(request)
        operation = _operation(request.method, request.url.path)
        supplied = request.headers.get("Idempotency-Key") or request.headers.get("X-Request-ID")
        if request.method in {"GET", "HEAD", "OPTIONS"} and not supplied:
            return await call_next(request)
        request_id = (
            f"http:{hashlib.sha256(f'{surface}:{operation}:{supplied}'.encode()).hexdigest()}"
            if supplied else f"http:{uuid.uuid4().hex}"
        )
        adapter = SurfaceRuntimeAdapter()
        acceptance = await asyncio.to_thread(
            adapter.safe_accept,
            surface=surface,
            operation=operation,
            request_id=request_id,
            session_id="mission-control-api",
            actor=f"api:{surface}",
        )
        try:
            response = await call_next(request)
        except BaseException:
            await asyncio.to_thread(
                adapter.safe_observe,
                acceptance,
                outcome="failed",
                evidence_refs=(f"http:{surface}:failed",),
            )
            raise
        outcome = "succeeded" if response.status_code < 400 else "failed"
        await asyncio.to_thread(
            adapter.safe_observe,
            acceptance,
            outcome=outcome,
            evidence_refs=(f"http:{surface}:{response.status_code}",),
        )
        return response
