"""Validated local-only job inputs and bounded worker policy."""

import math
import os
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from ..models import Model

TERMINAL = frozenset({"succeeded", "failed"})
MAX_RESULT_BYTES = 2_000_000


class JobRequest(Model):
    schema_version: Literal[1] = 1
    task_id: str = Field(default="q001", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    demo: Literal["none", "fail_once", "always_fail", "sleep", "effect"] = "none"
    delay_seconds: float = Field(default=0.0, ge=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def delay_requires_demo(self) -> "JobRequest":
        if self.delay_seconds and self.demo not in {"sleep", "effect"}:
            raise ValueError("Delay is available only for bounded synthetic demonstrations")
        return self


@dataclass(frozen=True)
class Policy:
    max_attempts: int = 3
    attempt_seconds: float = 30.0
    job_seconds: float = 120.0
    lease_seconds: float = 15.0
    heartbeat_seconds: float = 5.0
    poll_seconds: float = 0.2
    backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be an integer in [1,10]")
        for name in (
            "attempt_seconds",
            "job_seconds",
            "lease_seconds",
            "heartbeat_seconds",
            "poll_seconds",
            "backoff_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not 1 <= self.attempt_seconds <= self.job_seconds <= 600:
            raise ValueError("Require 1 <= attempt_seconds <= job_seconds <= 600")
        if not 1 <= self.lease_seconds <= 60 or self.heartbeat_seconds * 2 > self.lease_seconds:
            raise ValueError("Lease must be [1,60] seconds and at least two heartbeats")
        if self.poll_seconds > 5 or self.backoff_seconds > 5:
            raise ValueError("Poll and initial backoff must be at most 5 seconds")

    @classmethod
    def from_env(cls) -> "Policy":
        names = {
            "max_attempts": int,
            "attempt_seconds": float,
            "job_seconds": float,
            "lease_seconds": float,
            "heartbeat_seconds": float,
            "poll_seconds": float,
            "backoff_seconds": float,
        }
        values = {
            name: convert(os.environ["ARH_WORKFLOW_" + name.upper()])
            for name, convert in names.items()
            if "ARH_WORKFLOW_" + name.upper() in os.environ
        }
        return cls(**values)


def backoff(attempt: int, initial: float) -> float:
    """Deterministic capped backoff; actual next-run time is persisted."""
    return min(5.0, initial * 2 ** min(max(attempt - 1, 0), 10))


def database_url() -> str:
    if os.environ.get("ARH_WORKFLOW_MODE", "local") != "local":
        raise ValueError("Stage 1 supports local demonstrations only")
    value = os.environ.get("ARH_WORKFLOW_DATABASE_URL", "")
    if not value.startswith(("postgresql://", "postgres://")):
        raise ValueError("ARH_WORKFLOW_DATABASE_URL must identify a separate PostgreSQL database")
    return value
