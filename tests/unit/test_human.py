import pytest

from agent_reliability.evaluation.human import agreement, blinded_export


def test_no_synthetic_or_test_traces_in_human_validation(tmp_path):
    rows = [
        {
            "origin": "synthetic",
            "mode": "record",
            "split": "dev",
            "correct": False,
            "attempt_id": "s",
        },
        {"origin": "live", "mode": "record", "split": "test", "correct": False, "attempt_id": "t"},
        {
            "origin": "live",
            "mode": "record",
            "split": "dev",
            "correct": False,
            "attempt_id": "d",
            "trace_path": "d.json",
        },
    ]
    assert blinded_export(rows, tmp_path / "labels.csv", {"d"}) == 0
    assert "failure_category" not in (tmp_path / "labels.csv").read_text()


def test_agreement_is_classifier_vs_human():
    result = agreement(["loop", "unknown"], ["loop", "bad_arguments"])
    assert result["accuracy"] == 0.5
    assert result["n"] == 2
    with pytest.raises(ValueError):
        agreement([], [])
