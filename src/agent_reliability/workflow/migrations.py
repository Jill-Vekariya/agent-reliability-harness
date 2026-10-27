"""Checksummed forward SQL migrations; never recreate or erase a database."""

import hashlib
from pathlib import Path

import psycopg

MIGRATION_LOCK = 734621109


def migrate(url: str) -> None:
    with psycopg.connect(url, connect_timeout=3) as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS workflow_schema_migrations "
            "(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL "
            "DEFAULT clock_timestamp())"
        )
        files = sorted(Path(__file__).with_name("sql").glob("*.sql"))
        expected = {f.name for f in files}
        applied: dict[str, str] = dict(
            conn.execute("SELECT version,sha256 FROM workflow_schema_migrations").fetchall()
        )
        if not set(applied) <= expected:
            raise ValueError("Database has unsupported newer workflow migrations")
        for path in files:
            contents = path.read_bytes()
            checksum = hashlib.sha256(contents).hexdigest()
            if path.name in applied:
                if checksum != applied[path.name]:
                    raise ValueError("Applied workflow migration checksum changed")
                continue
            conn.execute(contents.decode("utf-8"), prepare=False)
            conn.execute(
                "INSERT INTO workflow_schema_migrations(version,sha256) VALUES(%s,%s)",
                (path.name, checksum),
            )
