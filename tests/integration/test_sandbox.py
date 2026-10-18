import hashlib
import os

import pytest

from agent_reliability.models import Limits
from agent_reliability.sandbox import Sandbox


@pytest.mark.parametrize(
    "sql,rows",
    [
        ("SELECT COUNT(*) FROM Artist", [[275]]),
        ("-- comment\n SeLeCt 1", [[1]]),
        ("WITH x AS (SELECT 2 AS v) SELECT v FROM x", [[2]]),
        ("SELECT 'a;b'", [["a;b"]]),
        ("SELECT Name FROM Artist WHERE ArtistId=1", [["AC/DC"]]),
    ],
)
def test_legitimate(sandbox, sql, rows):
    result = sandbox.run(sql)
    assert result.ok, result.error
    assert result.rows == rows


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM Artist",
        "dRoP TABLE Artist",
        "UPDATE Artist SET Name='bad'",
        "CREATE TABLE pwn(x)",
        "ATTACH DATABASE ':memory:' AS extra",
        "DETACH DATABASE main",
        "PRAGMA writable_schema=ON",
        "SELECT load_extension('missing')",
        "SELECT * FROM sqlite_master",
        "VACUUM",
        "BEGIN",
        "SELECT 1; SELECT 2",
        "SELECT readfile('/etc/passwd')",
        "SELECT * FROM MissingTable",
        "SELEC 1",
    ],
)
def test_rejects_without_modification(sandbox, sql):
    before = hashlib.sha256(sandbox.database.read_bytes()).hexdigest()
    result = sandbox.run(sql)
    assert not result.ok
    assert hashlib.sha256(sandbox.database.read_bytes()).hexdigest() == before


def test_authorizer_records_block(sandbox):
    assert sandbox.run("DELETE FROM Artist").blocked


def test_row_cap_and_cell_cap(sandbox):
    capped = Sandbox(sandbox.database, Limits(max_rows=2))
    result = capped.run("SELECT Name FROM Artist")
    assert result.ok and result.truncated and len(result.rows) == 2
    capped = Sandbox(sandbox.database, Limits(max_cell_bytes=8))
    assert capped.run("SELECT printf('%1000s','x')").truncated


def test_runtime_value_limit(sandbox):
    result = sandbox.run("SELECT hex(zeroblob(10000000))")
    assert not result.ok and result.resource_limited


def test_instruction_budget_and_cleanup(sandbox):
    result = sandbox.run(
        "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x"
    )
    assert not result.ok and result.resource_limited
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(sandbox.last_pid, 0)


def test_parent_wall_deadline(sandbox):
    limited = Sandbox(sandbox.database, Limits(wall_seconds=0.001))
    result = limited.run(
        "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x"
    )
    assert not result.ok and result.resource_limited


def test_schema_identifier_allowlist(sandbox):
    with pytest.raises(ValueError):
        sandbox.describe("Artist); DROP TABLE Artist;--")
    assert sandbox.describe("Track")["foreign_keys"]


def test_bad_input(sandbox):
    for sql in ["", "SELECT 1\x00", "x" * 20000]:
        assert not sandbox.run(sql).ok
