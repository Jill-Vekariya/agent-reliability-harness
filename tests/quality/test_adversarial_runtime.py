import pytest

from agent_reliability.tools.runtime import ToolRuntime


@pytest.mark.parametrize("sql", [
    "DROP TABLE Artist",
    "DELETE FROM Artist",
    "UPDATE Artist SET Name = 'changed'",
    "INSERT INTO Artist (ArtistId, Name) VALUES (999999, 'changed')",
    "ATTACH DATABASE ':memory:' AS external_db",
    "SELECT 1; DELETE FROM Artist",
])
def test_mutating_sql_never_succeeds(sandbox, sql):
    before = sandbox.run("SELECT COUNT(*) FROM Artist")
    assert before.ok
    runtime = ToolRuntime(sandbox)
    result = runtime.call("run_sql", {"sql": sql})
    assert not result["ok"]
    after = sandbox.run("SELECT COUNT(*) FROM Artist")
    assert after.ok
    assert after.rows == before.rows


@pytest.mark.parametrize("name,args", [
    ("shell", {"command": "id"}),
    ("run_sql", {"sql": "SELECT 1", "bypass": True}),
    ("run_sql", {"sql": 42}),
    ("describe_table", {"table": None}),
    ("final_answer", {"status": "answered", "result_id": "r999"}),
])
def test_invalid_tool_requests_rejected(sandbox, name, args):
    runtime = ToolRuntime(sandbox)
    assert "error" in runtime.call(name, args)
    assert runtime.final is None


def test_fabricated_answer_rows_rejected(sandbox):
    runtime = ToolRuntime(sandbox)
    result = runtime.call("run_sql", {"sql": "SELECT 1 AS value"})
    assert result["ok"]
    response = runtime.call("final_answer", {
        "status": "answered", "result_id": result["result_id"], "rows": [[999]],
    })
    assert "error" in response
    assert runtime.final is None
