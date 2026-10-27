"""Local fixture-job API. Stage 1 has no tenant or production authentication."""

import logging
import uuid
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..util import canonical
from .catalog import resolved_payload
from .models import JobRequest
from .store import IdempotencyConflict, Store

log = logging.getLogger(__name__)


def job_view(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in {"lease_token", "idempotency_key"}}


class BodyLimit:
    def __init__(self, app: Any, limit: int = 4096) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            part = message.get("body", b"")
            if len(body) + len(part) > self.limit:
                await JSONResponse({"detail": "Request body limit exceeded"}, 413)(
                    scope, receive, send
                )
                return
            body.extend(part)
            if not message.get("more_body", False):
                break
        sent = False

        async def bounded_receive() -> Any:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(root: Path, store: Store) -> FastAPI:
    app = FastAPI(title="Harness durable fixture jobs — local demonstration", version="stage1")
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def correlation(request: Request, call_next: Any) -> Any:
        request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        log.info(
            canonical(
                {
                    "event": "http",
                    "request_id": request_id,
                    "route": route.path if route else "unmatched",
                    "status": response.status_code,
                }
            )
        )
        return response

    @app.exception_handler(psycopg.Error)
    async def database_failure(request: Request, exc: psycopg.Error) -> JSONResponse:
        return JSONResponse({"detail": "Workflow database unavailable"}, status_code=503)

    @app.get("/live")
    def live() -> dict[str, str]:
        return {"status": "alive", "mode": "local-synthetic"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        if not store.ready():
            raise HTTPException(503, "Workflow migration required")
        return {"status": "ready", "mode": "local-synthetic"}

    @app.post("/jobs")
    def submit(
        body: JobRequest, idempotency_key: str = Header(alias="Idempotency-Key")
    ) -> JSONResponse:
        try:
            row, created = store.submit(idempotency_key, resolved_payload(root, body))
        except IdempotencyConflict as exc:
            raise HTTPException(409, "Idempotency key payload conflict") from exc
        except ValueError as exc:
            raise HTTPException(422, "Invalid fixture request or idempotency key") from exc
        return JSONResponse(
            jsonable_encoder(job_view(row)),
            status_code=201 if created else 200,
            headers={"Location": f"/jobs/{row['id']}"},
        )

    @app.get("/jobs")
    def jobs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
        return [job_view(row) for row in store.list_jobs(limit)]

    @app.get("/jobs/{job_id}")
    def job(job_id: uuid.UUID) -> dict[str, Any]:
        row = store.get(str(job_id))
        if row is None:
            raise HTTPException(404, "Job unavailable")
        return job_view(row)

    @app.get("/jobs/{job_id}/attempts")
    def attempts(job_id: uuid.UUID) -> list[dict[str, Any]]:
        if store.get(str(job_id)) is None:
            raise HTTPException(404, "Job unavailable")
        return [
            {k: v for k, v in row.items() if k != "token"} for row in store.attempts(str(job_id))
        ]

    return app
