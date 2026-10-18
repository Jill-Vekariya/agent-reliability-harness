from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_reliability.providers.budget import BudgetExceeded, Ledger


def test_zero_and_unknown_fail_closed(tmp_path):
    ledger = Ledger(tmp_path / "zero.sqlite", "0", "1")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("t", "0.1")
    ledger = Ledger(tmp_path / "live.sqlite", "1", "1")
    key = ledger.reserve("t", "0.4")
    ledger.reconcile(key, None)
    assert ledger.summary()["reserved_usd"] == "0.4"
    with pytest.raises(BudgetExceeded):
        ledger.reserve("next", "0.1")


def test_atomic_concurrent_reservations(tmp_path):
    ledger = Ledger(tmp_path / "spend.sqlite", "1", "1")

    def reserve(i):
        try:
            return ledger.reserve(str(i), "0.2")
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        keys = list(pool.map(reserve, range(20)))
    assert sum(k is not None for k in keys) == 5
    assert ledger.summary()["reserved_usd"] == "1"


def test_reconcile_and_per_task_cap(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite", "2", "0.5")
    key = ledger.reserve("t", "0.4")
    ledger.reconcile(key, "0.1")
    ledger.reserve("t", "0.4")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("t", "0.01")
    with pytest.raises(ValueError):
        ledger.reconcile(key, "0.1")


def test_authorized_caps_round_down_while_exposure_rounds_up(tmp_path):
    ledger = Ledger(tmp_path / "tiny.sqlite", "0.0000009", "1")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("tiny", "0.0000001")
    ledger = Ledger(tmp_path / "task.sqlite", "1", "0.0000019")
    ledger.reserve("t", "0.0000001")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("t", "0.0000001")


def test_over_reservation_charge_is_visible_and_freezes_ledger(tmp_path):
    ledger = Ledger(tmp_path / "overrun.sqlite", "1", "1")
    key = ledger.reserve("t", "0.2")
    with pytest.raises(BudgetExceeded):
        ledger.reconcile(key, "0.3")
    assert ledger.summary()["reserved_usd"] == "0.3"
    with pytest.raises(BudgetExceeded):
        ledger.reserve("other", "0.01")


def test_interrupted_reservation_survives_reopen_and_verified_zero_settlement(tmp_path):
    path = tmp_path / "crash.sqlite"
    key = Ledger(path, "0.5", "0.5").reserve("attempt", "0.5")
    reopened = Ledger(path, "0.5", "0.5")
    with pytest.raises(BudgetExceeded):
        reopened.reserve("next", "0.000001")
    # Zero is a trusted reconciliation result, never an automatic timeout release.
    reopened.reconcile(key, "0")
    reopened.reserve("next", "0.5")


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_invalid_amount_does_not_release_outstanding_exposure(tmp_path, value):
    ledger = Ledger(tmp_path / "invalid.sqlite", "1", "1")
    key = ledger.reserve("t", "0.2")
    with pytest.raises(ValueError):
        ledger.reconcile(key, value)
    assert ledger.summary()["reserved_usd"] == "0.2"
