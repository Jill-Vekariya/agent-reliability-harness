"""Short PostgreSQL transactions are the sole authority for job ownership."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..util import canonical, digest
from .migrations import expected_checksums
from .models import MAX_RESULT_BYTES, TERMINAL, Policy, backoff


class IdempotencyConflict(ValueError):
    pass


class ControlConflict(ValueError):
    pass


@dataclass(frozen=True)
class Claim:
    job_id: str
    number: int
    token: str
    worker_id: str
    payload: dict[str, Any]
    timeout_seconds: float
    tenant_id: str = "local-demo"
    request_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None


class Store:
    def __init__(self, url: str, policy: Policy | None = None) -> None:
        self._url = url
        self._options = str(conninfo_to_dict(url).get("options") or "")
        self.policy = policy or Policy()

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(
            self._url,
            row_factory=dict_row,
            connect_timeout=3,
            options=self._options + " -c statement_timeout=5000 -c lock_timeout=3000",
        )

    def ready(self) -> bool:
        with self.connect() as conn:
            rows = conn.execute("SELECT version,sha256 FROM workflow_schema_migrations").fetchall()
            return {r["version"]: r["sha256"] for r in rows} == expected_checksums()

    def submit(
        self,
        key: str,
        payload: dict[str, Any],
        tenant_id: str = "local-demo",
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if (
            not key
            or len(key) > 128
            or not key.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in key)
        ):
            raise ValueError(
                "Idempotency-Key must be 1-128 printable ASCII characters without spaces"
            )
        encoded = canonical(payload)
        if len(encoded.encode()) > 8192:
            raise ValueError("Job payload limit exceeded")
        payload_hash = digest(payload)
        request = payload.get("request", {})
        approval = bool(
            request.get("require_approval") or request.get("demo") in {"effect", "provider"}
        )
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO workflow_jobs(
                    id,namespace,idempotency_key,payload_hash,payload,state,
                    max_attempts,attempt_seconds,backoff_seconds,deadline_at,approval_required,
                    request_id,trace_id,parent_span_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       clock_timestamp() + %s * interval '1 second',%s,%s,%s,%s)
                ON CONFLICT(namespace,idempotency_key) DO NOTHING RETURNING *
                """,
                (
                    uuid.uuid4(),
                    tenant_id,
                    key,
                    payload_hash,
                    Jsonb(payload),
                    "waiting_approval" if approval else "queued",
                    self.policy.max_attempts,
                    self.policy.attempt_seconds,
                    self.policy.backoff_seconds,
                    self.policy.job_seconds,
                    approval,
                    request_id,
                    trace_id,
                    parent_span_id,
                ),
            ).fetchone()
            if row is not None:
                if approval:
                    self._new_approval(conn, row, 1)
                return row, True
            row = conn.execute(
                "SELECT * FROM workflow_jobs WHERE namespace=%s AND idempotency_key=%s",
                (tenant_id, key),
            ).fetchone()
            if (
                row is None
                or row["payload_hash"] != payload_hash
                or row["payload"] != json.loads(encoded)
            ):
                raise IdempotencyConflict("Idempotency key already identifies a different request")
            return row, False

    def get(self, job_id: str, tenant_id: str = "local-demo") -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM workflow_jobs WHERE id=%s AND namespace=%s", (job_id, tenant_id)
            ).fetchone()

    def list_jobs(
        self,
        limit: int = 20,
        tenant_id: str = "local-demo",
        state: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("List limit must be [1,100]")
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT id,state,attempt_count,max_attempts,created_at,updated_at,started_at,"
                    "finished_at,error_code,lease_owner,payload_hash FROM workflow_jobs "
                    "WHERE namespace=%s AND (%s::text IS NULL OR state=%s) "
                    "AND (%s::text IS NULL OR payload->'request'->>'task_id'=%s) "
                    "ORDER BY created_at DESC,id DESC LIMIT %s",
                    (tenant_id, state, state, task_id, task_id, limit),
                ).fetchall()
            )

    def attempts(self, job_id: str, tenant_id: str = "local-demo") -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT a.* FROM workflow_attempts a JOIN workflow_jobs j ON a.job_id=j.id "
                    "WHERE a.job_id=%s AND j.namespace=%s ORDER BY a.number",
                    (job_id, tenant_id),
                ).fetchall()
            )

    def recover(self) -> int:
        """Retain lost attempts; never reset their number or the total deadline."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *,clock_timestamp() AS db_now FROM workflow_jobs
                WHERE (state='running' AND lease_expires_at <= clock_timestamp())
                   OR (state IN ('queued','retry_wait','running','waiting_approval') AND deadline_at <= clock_timestamp())
                   OR (state IN ('waiting_approval','queued') AND approval_required AND EXISTS(
                       SELECT 1 FROM workflow_approvals a WHERE a.job_id=workflow_jobs.id
                       AND a.attempt_number=attempt_count+1 AND a.expires_at<=clock_timestamp()))
                ORDER BY created_at,id LIMIT 100 FOR UPDATE SKIP LOCKED
                """
            ).fetchall()
            for row in rows:
                expired = row["deadline_at"] <= row["db_now"]
                cancelled = row["cancel_requested_at"] is not None
                approval_expired = (
                    row["state"] in {"waiting_approval", "queued"} and row["approval_required"]
                )
                code = (
                    "cancelled"
                    if cancelled
                    else "job_deadline"
                    if expired
                    else "approval_expired"
                    if approval_expired
                    else "lease_expired"
                )
                self._reconcile_operations(conn, row)
                if approval_expired:
                    conn.execute(
                        "UPDATE workflow_approvals SET state='expired' WHERE job_id=%s AND state IN ('pending','approved')",
                        (row["id"],),
                    )
                if row["state"] == "running":
                    conn.execute(
                        """
                        UPDATE workflow_attempts SET state=%s,error_code=%s,finished_at=clock_timestamp()
                        WHERE job_id=%s AND number=%s AND state='running'
                        """,
                        (
                            "cancelled" if cancelled else "timed_out" if expired else "lost",
                            code,
                            row["id"],
                            row["attempt_count"],
                        ),
                    )
                terminal = (
                    cancelled
                    or expired
                    or approval_expired
                    or row["attempt_count"] >= row["max_attempts"]
                )
                next_state = (
                    "cancelled"
                    if cancelled
                    else "failed"
                    if terminal
                    else "waiting_approval"
                    if row["approval_required"]
                    else "retry_wait"
                )
                if not terminal and row["approval_required"]:
                    self._new_approval(conn, row, row["attempt_count"] + 1)
                conn.execute(
                    """
                    UPDATE workflow_jobs SET state=%s,error_code=%s,updated_at=clock_timestamp(),
                        finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,
                        next_run_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
                    WHERE id=%s
                    """,
                    (
                        next_state,
                        code,
                        terminal,
                        backoff(row["attempt_count"], row["backoff_seconds"]),
                        row["id"],
                    ),
                )
            return len(rows)

    def claim(self, worker_id: str) -> Claim | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("Bounded worker identity required")
        self.recover()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *,clock_timestamp() AS db_now FROM workflow_jobs
                WHERE state IN ('queued','retry_wait') AND next_run_at <= clock_timestamp()
                    AND deadline_at > clock_timestamp() AND attempt_count < max_attempts
                ORDER BY next_run_at,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if row is None:
                return None
            if row["cancel_requested_at"] is not None:
                return None
            if row["approval_required"]:
                approved = conn.execute(
                    "UPDATE workflow_approvals SET state='consumed',consumed_at=clock_timestamp() "
                    "WHERE job_id=%s AND attempt_number=%s AND state='approved' "
                    "AND action_hash=%s AND action_version=%s AND expires_at>clock_timestamp() RETURNING id",
                    (
                        row["id"],
                        row["attempt_count"] + 1,
                        row["payload_hash"],
                        row["action_version"],
                    ),
                ).fetchone()
                if approved is None:
                    return None
            token = uuid.uuid4()
            number = row["attempt_count"] + 1
            conn.execute(
                """
                UPDATE workflow_jobs SET state='running',attempt_count=%s,lease_owner=%s,
                    lease_token=%s,lease_expires_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                    updated_at=clock_timestamp(),started_at=COALESCE(started_at,clock_timestamp()),
                    error_code=NULL
                WHERE id=%s
                """,
                (number, worker_id, token, self.policy.lease_seconds, row["id"]),
            )
            conn.execute(
                "INSERT INTO workflow_attempts(job_id,number,token,worker_id,state) VALUES(%s,%s,%s,%s,'running')",
                (row["id"], number, token, worker_id),
            )
            remaining = (row["deadline_at"] - row["db_now"]).total_seconds()
            return Claim(
                str(row["id"]),
                number,
                str(token),
                worker_id,
                row["payload"],
                min(row["attempt_seconds"], max(0.01, remaining)),
                row["namespace"],
                row["request_id"],
                row["trace_id"],
                row["parent_span_id"],
            )

    def metrics(self, tenant_id: str) -> dict[str, Any]:
        """Bounded label sets and tenant authorization; no payloads or identifiers."""
        with self.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            jobs = conn.execute(
                "SELECT state,count(*) AS n FROM workflow_jobs WHERE namespace=%s GROUP BY state",
                (tenant_id,),
            ).fetchall()
            attempts = conn.execute(
                "SELECT a.state,count(*) AS n FROM workflow_attempts a JOIN workflow_jobs j ON j.id=a.job_id "
                "WHERE j.namespace=%s GROUP BY a.state",
                (tenant_id,),
            ).fetchall()
            queue = conn.execute(
                "SELECT COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-min(created_at)),0) AS age "
                "FROM workflow_jobs WHERE namespace=%s AND state IN ('queued','retry_wait')",
                (tenant_id,),
            ).fetchone()
            rejected = conn.execute(
                "SELECT COALESCE(sum(a.stale_result_rejections),0) AS n FROM workflow_attempts a "
                "JOIN workflow_jobs j ON j.id=a.job_id WHERE j.namespace=%s",
                (tenant_id,),
            ).fetchone()
            operations = conn.execute(
                "SELECT state,count(*) AS n FROM workflow_operations WHERE tenant_id=%s GROUP BY state",
                (tenant_id,),
            ).fetchall()
            budget = conn.execute(
                "SELECT limit_units,reserved_units,spent_units FROM workflow_budgets WHERE tenant_id=%s",
                (tenant_id,),
            ).fetchone()
        return {
            "jobs": {r["state"]: r["n"] for r in jobs},
            "attempts": {r["state"]: r["n"] for r in attempts},
            "operations": {r["state"]: r["n"] for r in operations},
            "queue_age_seconds": float(queue["age"]) if queue else 0.0,
            "stale_result_rejections": int(rejected["n"]) if rejected else 0,
            "budget": dict(budget) if budget else None,
        }

    def heartbeat(self, claim: Claim) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                UPDATE workflow_jobs SET
                    lease_expires_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                    updated_at=clock_timestamp()
                WHERE id=%s AND state='running' AND lease_token=%s AND attempt_count=%s
                    AND cancel_requested_at IS NULL AND lease_expires_at > clock_timestamp() AND deadline_at > clock_timestamp()
                RETURNING id
                """,
                (self.policy.lease_seconds, claim.job_id, claim.token, claim.number),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE workflow_attempts SET heartbeat_at=clock_timestamp() WHERE job_id=%s AND number=%s AND token=%s",
                (claim.job_id, claim.number, claim.token),
            )
            return True

    def finish(self, claim: Claim, result: dict[str, Any]) -> bool:
        if type(result.get("ok")) is not bool or len(canonical(result).encode()) > MAX_RESULT_BYTES:
            raise ValueError("Invalid or oversized attempt result")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT *,clock_timestamp() AS db_now FROM workflow_jobs WHERE id=%s FOR UPDATE",
                (claim.job_id,),
            ).fetchone()
            if (
                row is None
                or row["state"] != "running"
                or str(row["lease_token"]) != claim.token
                or row["attempt_count"] != claim.number
                or row["lease_expires_at"] <= row["db_now"]
                or row["deadline_at"] <= row["db_now"]
            ):
                conn.execute(
                    """
                    UPDATE workflow_attempts SET stale_result_rejections=stale_result_rejections+1,
                        last_rejection_at=clock_timestamp()
                    WHERE job_id=%s AND number=%s AND token=%s
                    """,
                    (claim.job_id, claim.number, claim.token),
                )
                return False
            ok = result["ok"]
            code = None if ok else str(result.get("error_code", "execution_failed"))[:80]
            retry = (
                not ok
                and result.get("retryable") is True
                and row["attempt_count"] < row["max_attempts"]
            )
            cancelled = row["cancel_requested_at"] is not None
            retry = retry and not cancelled
            state = (
                "cancelled"
                if cancelled
                else "succeeded"
                if ok
                else "waiting_approval"
                if retry and row["approval_required"]
                else "retry_wait"
                if retry
                else "failed"
            )
            attempt_state = (
                "succeeded" if ok else "timed_out" if code == "attempt_timeout" else "failed"
            )
            if cancelled:
                attempt_state, code = "cancelled", "cancelled"
            self._reconcile_operations(conn, row)
            # Check database time again at the actual state write, after acquiring the lock.
            accepted = conn.execute(
                """
                UPDATE workflow_jobs SET state=%s,result=%s,error_code=%s,updated_at=clock_timestamp(),
                    finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,
                    next_run_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
                WHERE id=%s AND state='running' AND lease_token=%s AND attempt_count=%s
                    AND lease_expires_at > clock_timestamp() AND deadline_at > clock_timestamp()
                RETURNING id
                """,
                (
                    state,
                    Jsonb(result) if state == "succeeded" else None,
                    code,
                    state in TERMINAL,
                    backoff(claim.number, row["backoff_seconds"]),
                    claim.job_id,
                    claim.token,
                    claim.number,
                ),
            ).fetchone()
            if accepted is None:
                conn.execute(
                    "UPDATE workflow_attempts SET stale_result_rejections=stale_result_rejections+1, "
                    "last_rejection_at=clock_timestamp() WHERE job_id=%s AND number=%s AND token=%s",
                    (claim.job_id, claim.number, claim.token),
                )
                return False
            conn.execute(
                """
                UPDATE workflow_attempts SET state=%s,error_code=%s,result=%s,finished_at=clock_timestamp()
                WHERE job_id=%s AND number=%s AND token=%s AND state='running'
                """,
                (attempt_state, code, Jsonb(result), claim.job_id, claim.number, claim.token),
            )
            if state == "waiting_approval":
                self._new_approval(conn, row, row["attempt_count"] + 1)
            return True

    @staticmethod
    def _new_approval(
        conn: psycopg.Connection[dict[str, Any]], job: dict[str, Any], number: int
    ) -> None:
        conn.execute(
            "INSERT INTO workflow_approvals(id,job_id,tenant_id,attempt_number,action_hash,action_version,state,expires_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,'pending',LEAST(%s,clock_timestamp()+interval '60 seconds'))",
            (
                uuid.uuid4(),
                job["id"],
                job["namespace"],
                number,
                job["payload_hash"],
                job["action_version"],
                job["deadline_at"],
            ),
        )

    def approvals(self, tenant_id: str, approval_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT a.*,j.payload->'request' AS proposed_action FROM workflow_approvals a "
                    "JOIN workflow_jobs j ON j.id=a.job_id WHERE a.tenant_id=%s "
                    "AND (%s::uuid IS NULL OR a.id=%s) ORDER BY a.created_at DESC,a.id LIMIT 100",
                    (tenant_id, approval_id, approval_id),
                ).fetchall()
            )

    def decide(
        self,
        tenant_id: str,
        approval_id: str,
        subject: str,
        decision: str,
        action_hash: str,
        action_version: int,
    ) -> dict[str, Any] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Invalid approval decision")
        with self.connect() as conn:
            # All control writes lock job before approval/operation before budget.
            job = conn.execute(
                "SELECT j.* FROM workflow_jobs j JOIN workflow_approvals a ON a.job_id=j.id "
                "WHERE a.id=%s AND j.namespace=%s FOR UPDATE OF j",
                (approval_id, tenant_id),
            ).fetchone()
            if job is None:
                return None
            approval = conn.execute(
                "SELECT *,clock_timestamp() AS db_now FROM workflow_approvals WHERE id=%s FOR UPDATE",
                (approval_id,),
            ).fetchone()
            assert approval is not None
            if (
                job["state"] != "waiting_approval"
                or approval["state"] != "pending"
                or approval["expires_at"] <= approval["db_now"]
                or job["deadline_at"] <= approval["db_now"]
                or approval["action_hash"] != action_hash
                or job["payload_hash"] != action_hash
                or approval["action_version"] != action_version
                or job["action_version"] != action_version
                or approval["attempt_number"] != job["attempt_count"] + 1
            ):
                raise ControlConflict("Approval unavailable, expired, reused or action changed")
            changed = conn.execute(
                "UPDATE workflow_approvals SET state=%s,approver=%s,decided_at=clock_timestamp() "
                "WHERE id=%s AND expires_at>clock_timestamp() RETURNING *",
                (decision, subject, approval_id),
            ).fetchone()
            if changed is None:
                raise ControlConflict("Approval expired")
            conn.execute(
                "UPDATE workflow_jobs SET state=%s,error_code=%s,updated_at=clock_timestamp(),"
                "finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE id=%s",
                (
                    "queued" if decision == "approved" else "failed",
                    None if decision == "approved" else "approval_rejected",
                    decision == "rejected",
                    job["id"],
                ),
            )
            return changed

    def cancel(self, job_id: str, tenant_id: str, subject: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            job = conn.execute(
                "SELECT * FROM workflow_jobs WHERE id=%s AND namespace=%s FOR UPDATE",
                (job_id, tenant_id),
            ).fetchone()
            if job is None:
                return None
            if job["state"] in TERMINAL:
                if job["state"] == "cancelled":
                    return job
                raise ControlConflict("Job already completed; cancellation was not accepted")
            if job["cancel_requested_at"] is not None:
                return job
            conn.execute(
                "UPDATE workflow_approvals SET state='cancelled' WHERE job_id=%s AND state IN ('pending','approved')",
                (job_id,),
            )
            running = job["state"] == "running"
            return conn.execute(
                "UPDATE workflow_jobs SET cancel_requested_at=clock_timestamp(),cancelled_by=%s,"
                "state=%s,error_code=%s,updated_at=clock_timestamp(),"
                "finished_at=CASE WHEN %s THEN NULL ELSE clock_timestamp() END WHERE id=%s RETURNING *",
                (
                    subject,
                    "running" if running else "cancelled",
                    "cancel_requested" if running else "cancelled",
                    running,
                    job_id,
                ),
            ).fetchone()

    def set_budget(self, tenant_id: str, limit_units: int) -> None:
        """Trusted operator only. Units are synthetic credits, never dollars."""
        if type(limit_units) is not int or not 0 <= limit_units <= 1_000_000_000:
            raise ValueError("Bounded nonnegative integer budget required")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO workflow_budgets(tenant_id,limit_units) VALUES(%s,%s) "
                "ON CONFLICT(tenant_id) DO UPDATE SET limit_units=EXCLUDED.limit_units",
                (tenant_id, limit_units),
            )

    def budget(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM workflow_budgets WHERE tenant_id=%s", (tenant_id,)
            ).fetchone()

    def operations(self, job_id: str, tenant_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM workflow_operations WHERE job_id=%s AND tenant_id=%s ORDER BY attempt_number",
                    (job_id, tenant_id),
                ).fetchall()
            )

    @staticmethod
    def _valid_claim(job: dict[str, Any] | None, claim: Claim) -> bool:
        return bool(
            job
            and job["state"] == "running"
            and str(job["lease_token"]) == claim.token
            and job["attempt_count"] == claim.number
            and job["namespace"] == claim.tenant_id
            and job["lease_expires_at"] > job["db_now"]
            and job["deadline_at"] > job["db_now"]
        )

    def reserve(self, claim: Claim, units: int | None) -> str:
        """Commit the maximum quote before dispatch; duplicate reservations are denied."""
        if units is None:
            raise ControlConflict("pricing_unknown")
        if type(units) is not int or not 0 <= units <= 1_000_000_000:
            raise ValueError("Invalid conservative quote")
        with self.connect() as conn:
            job = conn.execute(
                "SELECT *,clock_timestamp() AS db_now FROM workflow_jobs WHERE id=%s FOR UPDATE",
                (claim.job_id,),
            ).fetchone()
            if (
                not self._valid_claim(job, claim)
                or job is None
                or job["cancel_requested_at"] is not None
            ):
                raise ControlConflict("dispatch_not_authorized")
            budget = conn.execute(
                "UPDATE workflow_budgets SET reserved_units=reserved_units+%s WHERE tenant_id=%s "
                "AND limit_units-spent_units-reserved_units >= %s RETURNING tenant_id",
                (units, job["namespace"], units),
            ).fetchone()
            if budget is None and units:
                raise ControlConflict("budget_unavailable")
            operation = uuid.uuid4()
            try:
                conn.execute(
                    "INSERT INTO workflow_operations(id,job_id,tenant_id,attempt_number,action_hash,state,reserved_units) "
                    "VALUES(%s,%s,%s,%s,%s,'reserved',%s)",
                    (
                        operation,
                        claim.job_id,
                        job["namespace"],
                        claim.number,
                        job["payload_hash"],
                        units,
                    ),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise ControlConflict("operation_already_reserved") from exc
            return str(operation)

    def dispatch(self, claim: Claim, operation: str) -> bool:
        """The persisted dispatch boundary. Cancellation serializes against this write."""
        with self.connect() as conn:
            job = conn.execute(
                "SELECT *,clock_timestamp() AS db_now FROM workflow_jobs WHERE id=%s FOR UPDATE",
                (claim.job_id,),
            ).fetchone()
            if (
                not self._valid_claim(job, claim)
                or job is None
                or job["cancel_requested_at"] is not None
            ):
                return False
            return (
                conn.execute(
                    "UPDATE workflow_operations SET state='in_flight',updated_at=clock_timestamp() "
                    "WHERE id=%s AND job_id=%s AND attempt_number=%s AND state='reserved' "
                    "AND action_hash=%s AND EXISTS (SELECT 1 FROM workflow_jobs j WHERE j.id=workflow_operations.job_id AND j.state='running' AND j.cancel_requested_at IS NULL AND j.lease_token=%s AND j.lease_expires_at>clock_timestamp() AND j.deadline_at>clock_timestamp()) RETURNING id",
                    (operation, claim.job_id, claim.number, job["payload_hash"], claim.token),
                ).fetchone()
                is not None
            )

    def settle(self, claim: Claim, operation: str, actual: int | None) -> bool:
        if actual is not None and (type(actual) is not int or not 0 <= actual <= 1_000_000_000):
            raise ValueError("Invalid actual usage")
        with self.connect() as conn:
            # A late provider response can establish billing even after cancellation/lease loss.
            # It cannot change the job result and must match this attempt's immutable token.
            job = conn.execute(
                "SELECT id FROM workflow_jobs WHERE id=%s FOR UPDATE", (claim.job_id,)
            ).fetchone()
            if job is None:
                return False
            op = conn.execute(
                "SELECT o.* FROM workflow_operations o JOIN workflow_attempts a "
                "ON a.job_id=o.job_id AND a.number=o.attempt_number WHERE o.id=%s "
                "AND o.job_id=%s AND o.attempt_number=%s AND a.token=%s "
                "AND o.state IN ('in_flight','uncertain') FOR UPDATE OF o",
                (operation, claim.job_id, claim.number, claim.token),
            ).fetchone()
            if op is None:
                return False
            if actual is None:
                conn.execute(
                    "UPDATE workflow_operations SET state='uncertain',updated_at=clock_timestamp() WHERE id=%s",
                    (operation,),
                )
            else:
                # Record actual usage even if the quote was exceeded; never hide overspend.
                conn.execute(
                    "UPDATE workflow_budgets SET reserved_units=reserved_units-%s,spent_units=spent_units+%s WHERE tenant_id=%s",
                    (op["reserved_units"], actual, op["tenant_id"]),
                )
                conn.execute(
                    "UPDATE workflow_operations SET state='succeeded',actual_units=%s,updated_at=clock_timestamp() WHERE id=%s",
                    (actual, operation),
                )
            return True

    @staticmethod
    def _reconcile_operations(
        conn: psycopg.Connection[dict[str, Any]], job: dict[str, Any]
    ) -> None:
        ops = conn.execute(
            "SELECT * FROM workflow_operations WHERE job_id=%s AND attempt_number=%s AND state IN ('reserved','in_flight') FOR UPDATE",
            (job["id"], job["attempt_count"]),
        ).fetchall()
        for op in ops:
            if op["state"] == "reserved":
                conn.execute(
                    "UPDATE workflow_budgets SET reserved_units=reserved_units-%s WHERE tenant_id=%s",
                    (op["reserved_units"], op["tenant_id"]),
                )
            conn.execute(
                "UPDATE workflow_operations SET state=%s,updated_at=clock_timestamp() WHERE id=%s",
                ("released" if op["state"] == "reserved" else "uncertain", op["id"]),
            )
