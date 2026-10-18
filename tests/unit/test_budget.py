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
