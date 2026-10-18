import json
from decimal import localcontext

import pytest

from agent_reliability.providers.budget import Ledger, cap_micros, micros
from agent_reliability.providers.openai_adapter import priced_usd
from agent_reliability.util import write_json


def test_failed_replace_preserves_previous_snapshot_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "summary.json"
    write_json(path, {"state": "complete"})

    def interrupted(*args):
        raise OSError("simulated replacement interruption")

    monkeypatch.setattr("agent_reliability.util.os.replace", interrupted)
    with pytest.raises(OSError):
        write_json(path, {"state": "partial"})
    assert json.loads(path.read_text()) == {"state": "complete"}
    assert list(tmp_path.iterdir()) == [path]


def test_nonfinite_data_cannot_replace_valid_snapshot(tmp_path):
    path = tmp_path / "trace.json"
    write_json(path, {"valid": True})
    with pytest.raises(ValueError):
        write_json(path, {"nan": float("nan")})
    assert json.loads(path.read_text()) == {"valid": True}


def test_money_rounding_is_exact_even_with_low_decimal_precision():
    with localcontext() as context:
        context.prec = 3
        assert micros("0.0000010000000000000000000000000001") == 2
        assert cap_micros("0.0000019999999999999999999999999999") == 1
        assert (
            priced_usd(
                {
                    "input_usd_per_million": "1.000000000000000000000000000001",
                    "cached_input_usd_per_million": "0",
                    "output_usd_per_million": "0",
                },
                1,
                0,
                0,
            )
            == "0.000002"
        )


def test_ledger_summary_does_not_round_exposure_under_low_decimal_precision(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite", "1.234567", "1.234567")
    ledger.reserve("attempt", "1.234567")
    with localcontext() as context:
        context.prec = 3
        assert ledger.summary()["reserved_usd"] == "1.234567"
