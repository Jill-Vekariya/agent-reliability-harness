"""Parent-enforced worker lifetime and bounded JSON output."""

import json
import os
import selectors
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..models import Limits, SQLResult


class Sandbox:
    def __init__(self, database: Path, limits: Limits | None = None) -> None:
        self.database = database.resolve(strict=True)
        self.limits = limits or Limits()
        self.last_pid: int | None = None
        with sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True) as conn:
            self.tables = sorted(
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )
            self.schema: dict[str, Any] = {}
            for name in self.tables:
                identifier = '"' + name.replace('"', '""') + '"'
                self.schema[name] = {
                    "table": name,
                    "columns": [dict(zip(
                        ["cid", "name", "type", "notnull", "default", "pk"], row, strict=True
                    )) for row in conn.execute(f"PRAGMA table_info({identifier})")],
                    "foreign_keys": [list(r) for r in conn.execute(f"PRAGMA foreign_key_list({identifier})")],
                }

    def describe(self, name: str) -> dict[str, Any]:
        if name not in self.schema:
            raise ValueError("Unknown or unapproved table")
        return self.schema[name]

    def run(self, sql: str) -> SQLResult:
        if not isinstance(sql, str) or not sql.strip():
            return SQLResult(ok=False, error="SQL must be nonempty text", error_kind="arguments")
        if len(sql.encode()) > self.limits.max_sql_bytes or "\x00" in sql:
            return SQLResult(ok=False, error="SQL size or encoding limit", error_kind="arguments")
        request = json.dumps({
            "database": str(self.database), "tables": self.tables,
            "sql": sql, "limits": self.limits.model_dump(),
        }).encode()
        worker = Path(__file__).with_name("worker.py")
        with tempfile.TemporaryDirectory(prefix="arh-worker-") as tmp:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", str(worker)], cwd=tmp,
                env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")} if os.name == "nt" else {},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self.last_pid = proc.pid
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(request)
                proc.stdin.close()
                # selectors on pipes is POSIX; Windows reference execution is Docker.
                if os.name == "nt":
                    raise RuntimeError("Use Docker on Windows for the isolated SQL worker")
                chunks = bytearray()
                deadline = time.monotonic() + self.limits.wall_seconds + 0.25
                with selectors.DefaultSelector() as selector:
                    selector.register(proc.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            return SQLResult(ok=False, error="Parent wall deadline", error_kind="resource", resource_limited=True)
                        ready = selector.select(remaining)
                        if not ready:
                            continue
                        part = os.read(proc.stdout.fileno(), 4096)
                        if not part:
                            break
                        chunks.extend(part)
                        if len(chunks) > self.limits.max_output_bytes:
                            return SQLResult(ok=False, error="Worker output limit", error_kind="resource", resource_limited=True)
                proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                if not chunks or proc.returncode:
                    return SQLResult(ok=False, error=f"Worker exit {proc.returncode}", error_kind="worker", resource_limited=bool(proc.returncode and proc.returncode < 0))
                return SQLResult.model_validate_json(chunks)
            except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                return SQLResult(ok=False, error=str(exc)[:500], error_kind="worker")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                if proc.stdout:
                    proc.stdout.close()
