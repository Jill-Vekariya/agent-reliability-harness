"""Explicit local demo credentials, never production identity or caller tenant headers."""

import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject: str
    can_approve: bool = False


class DemoAuth:
    def __init__(self, credentials: dict[str, Principal]) -> None:
        if not credentials:
            raise ValueError("Explicit local demonstration credentials required")
        for token, principal in credentials.items():
            if (
                len(token) < 24
                or not token.isascii()
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", principal.tenant_id)
                or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", principal.subject)
                or type(principal.can_approve) is not bool
            ):
                raise ValueError("Invalid local demonstration credential configuration")
        self._credentials = credentials.copy()

    @classmethod
    def from_env(cls) -> "DemoAuth":
        path = os.environ.get("ARH_WORKFLOW_AUTH_FILE")
        encoded = os.environ.get("ARH_WORKFLOW_AUTH_JSON")
        if not path and not encoded:
            raise ValueError(
                "Set ARH_WORKFLOW_AUTH_FILE or ARH_WORKFLOW_AUTH_JSON; no anonymous workflow access"
            )
        values = json.loads(Path(path).read_text(encoding="utf-8") if path else encoded or "{}")
        return cls({token: Principal(**value) for token, value in values.items()})

    def authenticate(self, request: Request) -> Principal:
        header = request.headers.get("Authorization", "")
        if len(header) <= 512 and header.startswith("Bearer "):
            token = header[7:]
            if token.isascii():
                for configured, principal in self._credentials.items():
                    if hmac.compare_digest(token, configured):
                        return principal
        raise HTTPException(
            401, "Local demo credentials required", headers={"WWW-Authenticate": "Bearer"}
        )
