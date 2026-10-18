import pytest

from agent_reliability.evaluation.statistics import (
    family_bootstrap,
    live_metrics,
    paired_difference,
    pass_at_k,
)


def test_pass_k():
    assert pass_at_k(5, 2, 1) == pytest.approx(0.4)
    assert pass_at_k(5, 2, 5) == 1
    assert pass_at_k(5, 0, 5) == 0
    with pytest.raises(ValueError):
        pass_at_k(4, 1, 5)


def test_family_pairs_are_reproducible():
    a = [
        {"task_id": str(i), "repetition": 0, "family_id": str(i // 2), "correct": False}
        for i in range(6)
    ]
    b = [{**r, "correct": True} for r in a]
    assert paired_difference(a, b, resamples=100)["ci95"] == (1.0, 1.0)
    with pytest.raises(ValueError):
        paired_difference(a, b[:-1])
    assert family_bootstrap(a, lambda r: sum(x["correct"] for x in r) / len(r), 100) == (0.0, 0.0)


def test_synthetic_not_live():
    assert live_metrics([{"origin": "synthetic"}])["status"] == "not yet measured"


def test_insufficient_fresh_attempts():
    rows = [
        dict(
            origin="live",
            mode="record",
            category="ordinary",
            task_id="q",
            family_id="f",
            attempt_id=str(i),
            repetition=i,
            correct=True,
            latency_ms=10,
            cost_usd="0.001",
        )
        for i in range(4)
    ]
    assert live_metrics(rows)["pass_at_5"] is None
    rows.append({**rows[0], "attempt_id": "4", "repetition": 4})
    assert live_metrics(rows)["pass_at_5"] == 1
