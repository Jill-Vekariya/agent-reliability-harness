"""Tenant-scoped local demo API. Explicit credentials are required at startup."""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import Field

from ..models import Model
from ..util import canonical
from .auth import DemoAuth, Principal
from .catalog import resolved_payload
from .models import JobRequest
from .store import ControlConflict, IdempotencyConflict, Store
from .telemetry import Telemetry, carrier, prometheus

log = logging.getLogger(__name__)


def safe_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    view = {k: result[k] for k in ("ok", "error_code", "retryable") if k in result}
    if isinstance(result.get("synthetic_effect"), dict):
        view["synthetic_effect"] = {
            "deduplicated": result["synthetic_effect"].get("deduplicated") is True
        }
    if isinstance(result.get("fake_provider"), dict):
        units = result["fake_provider"].get("usage_units")
        view["fake_provider"] = {
            "usage_units": units if type(units) is int and units >= 0 else None
        }
    # All raw prompts, SQL, rows, provider payloads and unknown fields stay private.
    if isinstance(result.get("grade"), dict):
        view["grade"] = {
            k: v for k, v in result["grade"].items() if isinstance(v, (bool, int, float))
        }
    trace = result.get("trace")
    if isinstance(trace, dict):
        view["trace"] = {"event_count": len(trace.get("events", [])), "redacted": True}
    return view


def job_view(row: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "state",
        "attempt_count",
        "max_attempts",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "deadline_at",
        "error_code",
        "payload_hash",
        "action_version",
        "approval_required",
        "cancel_requested_at",
    }
    view = {k: v for k, v in row.items() if k in allowed}
    if "result" in row:
        view["result"] = safe_result(row["result"])
    return view


def attempt_view(row: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "job_id",
        "number",
        "state",
        "started_at",
        "heartbeat_at",
        "finished_at",
        "error_code",
        "stale_result_rejections",
        "last_rejection_at",
    }
    return {
        **{k: v for k, v in row.items() if k in allowed},
        "result": safe_result(row.get("result")),
    }


class ApprovalDecision(Model):
    decision: Literal["approved", "rejected"]
    action_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    action_version: int = Field(ge=1)


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


def create_app(root: Path, store: Store, auth: DemoAuth | None = None) -> FastAPI:
    auth = auth or DemoAuth.from_env()
    authenticated = Depends(auth.authenticate)
    telemetry = Telemetry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        yield
        telemetry.close()

    app = FastAPI(
        title="Harness durable fixture jobs — authenticated local demonstration",
        version="stage5",
        lifespan=lifespan,
    )
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def correlation(request: Request, call_next: Any) -> Any:
        request_id = uuid.uuid4().hex
        with telemetry.span("workflow.http", request_id=request_id) as span:
            request.state.request_id = request_id
            response = await call_next(request)
            route = request.scope.get("route")
            span.set_attribute("route", route.path if route else "unmatched")
            span.set_attribute("status", response.status_code)
            if getattr(request.state, "job_id", None):
                span.set_attribute("job_id", request.state.job_id)
            trace_id = f"{span.get_span_context().trace_id:032x}"
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        log.info(
            canonical(
                {
                    "event": "http",
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "job_id": getattr(request.state, "job_id", None),
                    "route": route.path if route else "unmatched",
                    "status": response.status_code,
                }
            )
        )
        return response

    @app.exception_handler(psycopg.Error)
    async def database_failure(request: Request, exc: psycopg.Error) -> JSONResponse:
        return JSONResponse({"detail": "Workflow database unavailable"}, status_code=503)

    @app.exception_handler(ControlConflict)
    async def conflict(request: Request, exc: ControlConflict) -> JSONResponse:
        return JSONResponse(
            {"detail": "Control conflict: action unavailable, expired or already completed"},
            status_code=409,
        )

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
        body: JobRequest,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        principal: Principal = authenticated,
    ) -> JSONResponse:
        try:
            trace_id, parent_span_id = carrier()
            row, created = store.submit(
                idempotency_key,
                resolved_payload(root, body),
                principal.tenant_id,
                request_id=request.state.request_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(409, "Idempotency key payload conflict") from exc
        except ValueError as exc:
            raise HTTPException(422, "Invalid fixture request or idempotency key") from exc
        request.state.job_id = str(row["id"])
        return JSONResponse(
            jsonable_encoder(job_view(row)),
            status_code=201 if created else 200,
            headers={"Location": f"/jobs/{row['id']}"},
        )

    @app.get("/jobs")
    def jobs(
        limit: int = Query(default=20, ge=1, le=100),
        state: str | None = Query(default=None, max_length=32),
        task_id: str | None = Query(default=None, max_length=64),
        principal: Principal = authenticated,
    ) -> list[dict[str, Any]]:
        return [
            job_view(row) for row in store.list_jobs(limit, principal.tenant_id, state, task_id)
        ]

    def find(job_id: uuid.UUID, principal: Principal) -> dict[str, Any]:
        row = store.get(str(job_id), principal.tenant_id)
        if row is None:
            raise HTTPException(404, "Job unavailable")
        return row

    @app.get("/jobs/{job_id}")
    def job(job_id: uuid.UUID, principal: Principal = authenticated) -> dict[str, Any]:
        return job_view(find(job_id, principal))

    @app.get("/jobs/{job_id}/attempts")
    def attempts(job_id: uuid.UUID, principal: Principal = authenticated) -> list[dict[str, Any]]:
        find(job_id, principal)
        return [attempt_view(row) for row in store.attempts(str(job_id), principal.tenant_id)]

    @app.get("/jobs/{job_id}/result")
    def result(job_id: uuid.UUID, principal: Principal = authenticated) -> dict[str, Any] | None:
        return safe_result(find(job_id, principal)["result"])

    @app.get("/jobs/{job_id}/trace")
    def trace(job_id: uuid.UUID, principal: Principal = authenticated) -> list[dict[str, Any]]:
        find(job_id, principal)
        return [
            {"attempt": row["number"], "trace": (safe_result(row.get("result")) or {}).get("trace")}
            for row in store.attempts(str(job_id), principal.tenant_id)
        ]

    @app.post("/jobs/{job_id}/cancel")
    def cancel(job_id: uuid.UUID, principal: Principal = authenticated) -> JSONResponse:
        row = store.cancel(str(job_id), principal.tenant_id, principal.subject)
        if row is None:
            raise HTTPException(404, "Job unavailable")
        return JSONResponse(
            jsonable_encoder(job_view(row)), status_code=202 if row["state"] == "running" else 200
        )

    @app.get("/jobs/{job_id}/operations")
    def operations(job_id: uuid.UUID, principal: Principal = authenticated) -> list[dict[str, Any]]:
        find(job_id, principal)
        return store.operations(str(job_id), principal.tenant_id)

    @app.get("/approvals")
    def approvals(principal: Principal = authenticated) -> list[dict[str, Any]]:
        return store.approvals(principal.tenant_id)

    @app.get("/approvals/{approval_id}")
    def approval(approval_id: uuid.UUID, principal: Principal = authenticated) -> dict[str, Any]:
        rows = store.approvals(principal.tenant_id, str(approval_id))
        if not rows:
            raise HTTPException(404, "Approval unavailable")
        return rows[0]

    @app.post("/approvals/{approval_id}/decision")
    def decide(
        approval_id: uuid.UUID, body: ApprovalDecision, principal: Principal = authenticated
    ) -> dict[str, Any]:
        if not principal.can_approve:
            raise HTTPException(403, "Approver permission required")
        row = store.decide(
            principal.tenant_id,
            str(approval_id),
            principal.subject,
            body.decision,
            body.action_hash,
            body.action_version,
        )
        if row is None:
            raise HTTPException(404, "Approval unavailable")
        return row

    @app.get("/budget")
    def budget(principal: Principal = authenticated) -> dict[str, Any]:
        row = store.budget(principal.tenant_id)
        if row is None:
            raise HTTPException(404, "No synthetic budget configured")
        return {**row, "unit": "synthetic-credit", "live_provider_enabled": False}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics(principal: Principal = authenticated) -> PlainTextResponse:
        return PlainTextResponse(
            prometheus(store.metrics(principal.tenant_id)), media_type="text/plain; version=0.0.4"
        )

    return app
