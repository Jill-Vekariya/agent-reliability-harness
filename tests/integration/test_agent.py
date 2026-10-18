from agent_reliability.agents import SQLAgent
from agent_reliability.models import TaskInput
from agent_reliability.providers.fixture import FixtureProvider
from agent_reliability.tools.runtime import ToolRuntime


def test_fixture_flow(sandbox):
    provider = FixtureProvider([
        {"name": "list_tables", "arguments": {}},
        {"name": "run_sql", "arguments": {"sql": "SELECT COUNT(*) FROM Artist"}},
        {"name": "final_answer", "arguments": {"status": "answered", "result_id": "r001"}},
    ])
    trace = SQLAgent(provider, sandbox).run(TaskInput(id="opaque", question="How many artists?"))
    assert trace.final["rows"] == [[275]]
    assert trace.mode == "fixture" and trace.origin == "synthetic"


def test_final_answer_integrity(sandbox):
    runtime = ToolRuntime(sandbox)
    assert "error" in runtime.call("final_answer", {"status": "answered", "result_id": "r001"})
    result = runtime.call("run_sql", {"sql": "SELECT 1"})
    assert "error" in runtime.call("final_answer", {"status": "answered", "result_id": result["result_id"], "rows": [[2]]})
    other = ToolRuntime(sandbox)
    assert "error" in other.call("final_answer", {"status": "answered", "result_id": result["result_id"]})
    assert runtime.call("final_answer", {"status": "answered", "result_id": result["result_id"]})["accepted"]


def test_truncated_answer_rejected(sandbox):
    runtime = ToolRuntime(sandbox)
    result = runtime.call("run_sql", {"sql": "SELECT * FROM Track"})
    assert result["truncated"]
    assert "error" in runtime.call("final_answer", {"status": "answered", "result_id": result["result_id"]})
