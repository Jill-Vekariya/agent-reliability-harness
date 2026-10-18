from types import SimpleNamespace as NS

import pytest

from agent_reliability.providers.budget import BudgetExceeded, Ledger
from agent_reliability.providers.openai_adapter import OpenAIProvider
from agent_reliability.util import digest


def test_live_denied_before_client_initialization(tmp_path):
    with pytest.raises(BudgetExceeded):
        OpenAIProvider(
            {}, {"model": "pending"}, "tasks", Ledger(tmp_path / "l.sqlite", "0", "0"), "t"
        )


def test_billed_usage_with_fake_transport_and_unknown_charge(tmp_path, monkeypatch):
    monkeypatch.setenv("API_BUDGET_USD", "1")
    config = {"model": "test-only", "max_output_tokens": 20, "max_input_tokens": 8192}
    approval = dict(
        approved_by="SYNTHETIC TEST",
        approved_at="test",
        campaign_id="unit",
        official_pricing_url="test",
        pricing_checked_at="test",
        official_context_limit_url="test",
        config_hash=digest(config),
        task_hash="tasks",
        model="test-only",
        provider="openai",
        budget_usd="1",
        input_usd_per_million="1",
        cached_input_usd_per_million="0.5",
        output_usd_per_million="2",
        provider_context_window_tokens=10000,
    )
    response = NS(
        usage=NS(
            prompt_tokens=100, completion_tokens=10, prompt_tokens_details=NS(cached_tokens=20)
        ),
        model="test-only",
        choices=[
            NS(
                finish_reason="tool_calls",
                message=NS(
                    content=None, tool_calls=[NS(function=NS(name="list_tables", arguments="{}"))]
                ),
            )
        ],
    )
    requests = []

    def create(**kw):
        requests.append(kw)
        return response

    client = NS(chat=NS(completions=NS(create=create)))
    ledger = Ledger(tmp_path / "ledger.sqlite", "1", "1")
    provider = OpenAIProvider(approval, config, "tasks", ledger, "t", client=client)
    request = {"model": "test-only", "messages": [], "tools": [], "max_completion_tokens": 20}
    reply = provider.complete(request)
    assert reply.cost_usd == "0.00011"
    assert requests[0]["parallel_tool_calls"] is False
    assert ledger.summary()["reserved_usd"] == "0"
    response.usage = None
    with pytest.raises(BudgetExceeded):
        provider.complete(request)
    assert ledger.summary()["reserved_usd"] != "0"
