"""Minimal child process: no provider imports, credentials, or agent-controlled paths."""

import json
import math
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

FUNCTIONS = frozenset(
    "abs avg char coalesce count date datetime dense_rank glob group_concat ifnull iif "
    "instr julianday lag last_value lead length like lower ltrim max min nth_value nullif "
    "ntile printf rank replace round row_number rtrim strftime substr substring sum time "
    "total trim typeof unicode unixepoch upper hex zeroblob".split()
)


def execute(req: dict[str, Any]) -> dict[str, Any]:
    limits = req["limits"]
    try:
        import resource

        ram = limits["memory_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (ram, ram))
        resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"] + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except ImportError:
        pass  # Windows uses the documented Docker/Linux reference for OS limits.
    deadline = time.monotonic() + limits["wall_seconds"]
    conn = sqlite3.connect(Path(req["database"]).as_uri() + "?mode=ro", uri=True)
    blocked = False
    exhausted = False
    try:
        if hasattr(conn, "enable_load_extension"):
            conn.enable_load_extension(False)
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        for category, value in [
            (sqlite3.SQLITE_LIMIT_LENGTH, limits["max_value_bytes"]),
            (sqlite3.SQLITE_LIMIT_SQL_LENGTH, limits["max_sql_bytes"]),
            (sqlite3.SQLITE_LIMIT_COLUMN, 64),
            (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
            (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20),
            (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
        ]:
            conn.setlimit(category, value)
            if conn.getlimit(category) > value:
                raise RuntimeError("SQLite runtime limit was not applied")

        def authorize(code: int, a: str | None, b: str | None, db: str | None, _: str | None) -> int:
            nonlocal blocked
            allow = code in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE)
            if code == sqlite3.SQLITE_READ:
                # COUNT(*) can report no database name for its empty-column read.
                allow = db in (None, "main") and a in req["tables"]
            elif code == sqlite3.SQLITE_FUNCTION:
                allow = (b or "").lower() in FUNCTIONS
            if not allow:
                blocked = True
            return sqlite3.SQLITE_OK if allow else sqlite3.SQLITE_DENY

        ticks = 0

        def progress() -> int:
            nonlocal ticks, exhausted
            ticks += 100
            exhausted = ticks >= limits["max_vm_steps"] or time.monotonic() >= deadline
            return int(exhausted)

        conn.set_authorizer(authorize)
        conn.set_progress_handler(progress, 100)
        cursor = conn.execute(req["sql"])
        if cursor.description is None:
            return {"ok": False, "blocked": True, "error": "Read query required", "error_kind": "policy"}
        columns = [str(c[0]) for c in cursor.description]
        rows: list[list[Any]] = []
        used = len(json.dumps(columns).encode())
        truncated = False
        for idx, row in enumerate(cursor):
            if idx >= limits["max_rows"]:
                truncated = True
                break
            values: list[Any] = []
            for value in row:
                if isinstance(value, bytes):
                    value = {"$blob": value.hex()}
                if isinstance(value, float) and not math.isfinite(value):
                    return {"ok": False, "error": "Nonfinite numeric result", "error_kind": "nonfinite"}
                if len(json.dumps(value, ensure_ascii=False).encode()) > limits["max_cell_bytes"]:
                    truncated = True
                    break
                values.append(value)
            if truncated:
                break
            encoded = json.dumps(values, ensure_ascii=False, allow_nan=False).encode()
            used += len(encoded) + 1
            if used > limits["max_output_bytes"] - 1024:
                truncated = True
                break
            rows.append(values)
        return {"ok": True, "columns": columns, "rows": rows, "truncated": truncated}
    except sqlite3.Error as exc:
        message = str(exc)
        resource_hit = exhausted or "too big" in message or "too large" in message
        return {
            "ok": False, "error": message[:500], "blocked": blocked,
            "resource_limited": resource_hit,
            "error_kind": "policy" if blocked else "resource" if resource_hit else "sql",
        }
    finally:
        conn.close()


def main() -> None:
    try:
        req = json.loads(sys.stdin.buffer.read(200000))
        result = execute(req)
    except BaseException as exc:
        result = {"ok": False, "error": type(exc).__name__, "error_kind": "worker"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    os.environ.clear()
    main()
