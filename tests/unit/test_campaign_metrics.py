"""Synthetic observations exercise statistics; none are empirical model evidence."""

import json

import pytest

from agent_reliability.evaluation.statistics import live_metrics
from agent_reliability.reporting.report import build_report


def observations(task="q1", config="B"):
    return [
        dict(
            task_id=task,
            family_id=task,
            config=config,
            model="FAKE_TEST_MODEL",
            attempt_id=f"{config}:{task}:{i}",
            repetition=i,
            origin="live",
            mode="record",
            category="ordinary",
            split="dev",
            correct=i < 3,
            latency_ms=10.0 + i,
            cost_usd="0.001",
            tool_errors=int(i == 0),
            recovered_after_tool_error=i == 0,
            failure_category=None if i < 3 else "unknown",
            prohibited_executed=False,
            reason="Synthetic test only",
            trace_path="unused.json",
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=10,
        )
        for i in range(5)
    ]


def test_entire_missing_task_cannot_disappear_from_denominator():
    rows = observations()
    planned = rows + observations("q2")
    measured = live_metrics(rows, planned_attempts=planned, resamples=50)
    assert measured["planned_ordinary_attempts"] == 10
    assert measured["missing_expected_attempts"] == 5
    assert measured["status"] == "incomplete campaign"
    assert measured["pass_at_1"] is None and measured["pass_at_5"] is None
    assert measured["mean_cost_usd"] is None and measured["observed_mean_cost_usd"] == 0.001
    assert measured["observed_attempt_denominator"] == 5
    assert measured["correct_observed_attempts"] == 3


def test_complete_manifest_and_explicit_rate_denominators():
    rows = observations()
    result = live_metrics(rows, planned_attempts=rows, resamples=50)
    assert result["status"] == "measured" and result["coverage_verified"]
    assert result["pass_at_1"] == 0.6 and result["pass_at_5"] == 1
    assert result["first_sample_denominator"] == 1 and result["first_sample_successes"] == 1
    assert result["tool_error_attempts"] == 1 and result["retry_recovery_rate"] == 1
    assert result["input_tokens_observed_total"] == 500
    assert result["output_tokens_observed_total"] == 50
    assert live_metrics(rows, require_manifest=True, resamples=50)["pass_at_5"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("config", "A"),
        ("model", "OTHER_FAKE"),
        ("split", "test"),
        ("latency_ms", float("inf")),
        ("cost_usd", "NaN"),
        ("correct", 1),
        ("repetition", 9),
    ],
)
def test_invalid_or_mixed_measurements_are_rejected(field, value):
    rows = observations()
    rows[0][field] = value
    with pytest.raises(ValueError):
        live_metrics(rows, resamples=20)


def test_duplicate_identity_and_wrong_planned_scope_are_rejected():
    rows = observations()
    with pytest.raises(ValueError, match="Duplicate"):
        live_metrics(rows + rows[:1])
    with pytest.raises(ValueError, match="provenance"):
        live_metrics(rows, planned_attempts=observations("different"))


def test_missing_usage_and_no_error_denominator_remain_undefined():
    rows = [
        {**r, "cost_usd": None, "tool_errors": 0, "recovered_after_tool_error": False}
        for r in observations()
    ]
    measured = live_metrics(rows, planned_attempts=rows, resamples=30)
    assert measured["mean_cost_usd"] is None and measured["cost_per_success_usd"] is None
    assert measured["retry_recovery_rate"] is None
    result = live_metrics([], planned_attempts=rows)
    assert result["fresh_ordinary_attempts"] == 0 and result["missing_expected_attempts"] == 5


def test_partial_report_clears_old_measured_plot_and_does_not_pool_models(tmp_path):
    (tmp_path / "pareto.png").write_bytes(b"stale previous result")
    rows = observations()
    path = build_report({"rows": rows, "planned_attempts": rows + observations("q2")}, tmp_path)
    assert not (tmp_path / "pareto.png").exists()
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert "pass_at_1" not in metrics and metrics["by_configuration"]["B"]["pass_at_1"] is None
    assert "planned=10; missing=5" in path.read_text()


def test_saved_live_playback_is_not_described_as_free_synthetic_evidence(tmp_path):
    path = build_report({"rows": [{**r, "mode": "replay"} for r in observations()]}, tmp_path)
    content = path.read_text()
    assert "playback only" in content and "Fresh recorded attempts: 0" in content
    assert "USD 0" not in content and "scripted result matches" not in content


def test_zero_outcome_campaign_still_reports_coverage(tmp_path):
    path = build_report({"rows": [], "planned_attempts": observations()}, tmp_path)
    assert "no completed model outcomes" in path.read_text()
    assert "planned=5; missing=5" in path.read_text()
