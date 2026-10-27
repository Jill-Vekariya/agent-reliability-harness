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
from .models import MAX_RESULT_BYTES, Policy, backoff


class IdempotencyConflict(ValueError):
    pass


@dataclass(frozen=True)
class Claim:
    job_id: str
    number: int
    token: str
    worker_id: str
    payload: dict[str, Any]
    timeout_seconds: float


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
            row = conn.execute(
                "SELECT version FROM workflow_schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            return row is not None and row["version"] == "001_initial.sql"

    def submit(self, key: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
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
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO workflow_jobs(
                    id,namespace,idempotency_key,payload_hash,payload,state,
                    max_attempts,attempt_seconds,backoff_seconds,deadline_at)
                VALUES(%s,'local-demo',%s,%s,%s,'queued',%s,%s,%s,
                       clock_timestamp() + %s * interval '1 second')
                ON CONFLICT(namespace,idempotency_key) DO NOTHING RETURNING *
                """,
                (
                    uuid.uuid4(),
                    key,
                    payload_hash,
                    Jsonb(payload),
                    self.policy.max_attempts,
                    self.policy.attempt_seconds,
                    self.policy.backoff_seconds,
                    self.policy.job_seconds,
                ),
            ).fetchone()
            if row is not None:
                return row, True
            row = conn.execute(
                "SELECT * FROM workflow_jobs WHERE namespace='local-demo' AND idempotency_key=%s",
                (key,),
            ).fetchone()
            if (
                row is None
                or row["payload_hash"] != payload_hash
                or row["payload"] != json.loads(encoded)
            ):
                raise IdempotencyConflict("Idempotency key already identifies a different request")
            return row, False

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM workflow_jobs WHERE id=%s", (job_id,)).fetchone()

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("List limit must be [1,100]")
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT id,state,attempt_count,max_attempts,created_at,updated_at,started_at,"
                    "finished_at,error_code,lease_owner,payload_hash FROM workflow_jobs "
                    "ORDER BY created_at DESC,id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            )

    def attempts(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM workflow_attempts WHERE job_id=%s ORDER BY number", (job_id,)
                ).fetchall()
            )

    def recover(self) -> int:
        """Retain lost attempts; never reset their number or the total deadline."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *,clock_timestamp() AS db_now FROM workflow_jobs
                WHERE (state='running' AND lease_expires_at <= clock_timestamp())
                   OR (state IN ('queued','retry_wait','running') AND deadline_at <= clock_timestamp())
                ORDER BY created_at,id LIMIT 100 FOR UPDATE SKIP LOCKED
                """
            ).fetchall()
            for row in rows:
                expired = row["deadline_at"] <= row["db_now"]
                code = "job_deadline" if expired else "lease_expired"
                if row["state"] == "running":
                    conn.execute(
                        """
                        UPDATE workflow_attempts SET state=%s,error_code=%s,finished_at=clock_timestamp()
                        WHERE job_id=%s AND number=%s AND state='running'
                        """,
                        ("timed_out" if expired else "lost", code, row["id"], row["attempt_count"]),
                    )
                terminal = expired or row["attempt_count"] >= row["max_attempts"]
                conn.execute(
                    """
                    UPDATE workflow_jobs SET state=%s,error_code=%s,updated_at=clock_timestamp(),
                        finished_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,
                        next_run_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
                    WHERE id=%s
                    """,
                    (
                        "failed" if terminal else "retry_wait",
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
            )

    def heartbeat(self, claim: Claim) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                UPDATE workflow_jobs SET
                    lease_expires_at=LEAST(deadline_at,clock_timestamp() + %s * interval '1 second'),
                    updated_at=clock_timestamp()
                WHERE id=%s AND state='running' AND lease_token=%s AND attempt_count=%s
                    AND lease_expires_at > clock_timestamp() AND deadline_at > clock_timestamp()
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
            state = "succeeded" if ok else "retry_wait" if retry else "failed"
            attempt_state = (
                "succeeded" if ok else "timed_out" if code == "attempt_timeout" else "failed"
            )
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
                    Jsonb(result) if ok else None,
                    code,
                    state != "retry_wait",
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
            return True
