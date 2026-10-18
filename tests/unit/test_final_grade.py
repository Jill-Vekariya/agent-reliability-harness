from agent_reliability.evaluation.grading import grade
from agent_reliability.models import EvaluationTask, SQLResult, Trace


def test_forged_final_boolean_is_not_supported_integer():
    task = EvaluationTask(
        id="q",
        question="one",
        difficulty="easy",
        category="ordinary",
        family_id="f",
        gold_sql="SELECT 1",
        expected_columns=["n"],
        expected_result=[[1]],
    )
    trace = Trace(
        task_id="q",
        attempt_id="a",
        mode="fixture",
        origin="synthetic",
        config="test",
        results={"r001": SQLResult(ok=True, columns=["n"], rows=[[1]])},
        final={"status": "answered", "result_id": "r001", "columns": ["n"], "rows": [[True]]},
    )
    assert not grade(task, trace).correct
