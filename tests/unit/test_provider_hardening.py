"""All transports and approval/pricing values here are synthetic unit-test fixtures."""

from types import SimpleNamespace as NS

import pytest

from agent_reliability.providers.budget import BudgetExceeded, Ledger
from agent_reliability.providers.openai_adapter import OpenAIProvider
from agent_reliability.util import digest


@pytest.fixture
def transport(tmp_path, monkeypatch):
    monkeypatch.setenv("API_BUDGET_USD", "1")
    config = {"model": "synthetic-test", "max_output_tokens": 20}
    approval = dict(
        approved_by="SYNTHETIC TEST ONLY",
        approved_at="fixture",
        campaign_id="test",
        official_pricing_url="fixture",
        pricing_checked_at="fixture",
        official_context_limit_url="fixture",
        config_hash=digest(config),
        task_hash="test",
        model="synthetic-test",
        provider="openai",
        budget_usd="1",
        input_usd_per_million="1",
        cached_input_usd_per_million="0.5",
        output_usd_per_million="2",
        provider_context_window_tokens=10000,
    )
    response = NS(
        usage=NS(prompt_tokens=100, completion_tokens=10, prompt_tokens_details=None),
        model="synthetic-test",
        choices=[NS(finish_reason="stop", message=NS(content="", tool_calls=[]))],
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    ledger = Ledger(tmp_path / "spend.sqlite", "1", "1")
    provider = OpenAIProvider(
        approval, config, "test", ledger, "t", client=NS(chat=NS(completions=NS(create=create)))
    )
    request = {"model": "synthetic-test", "messages": [], "tools": [], "max_completion_tokens": 20}
    return provider, response, request, ledger, calls, config


@pytest.mark.parametrize(
    "fault", ["negative_output", "bool_input", "missing_fields", "excess_input", "negative_cache"]
)
def test_malformed_usage_retains_exposure_and_stops_more_dispatch(transport, fault):
    provider, response, request, ledger, calls, _ = transport
    if fault == "negative_output":
        response.usage.completion_tokens = -1
    elif fault == "bool_input":
        response.usage.prompt_tokens = True
    elif fault == "missing_fields":
        response.usage = NS()
    elif fault == "excess_input":
        response.usage.prompt_tokens = 10001
    else:
        response.usage.prompt_tokens_details = NS(cached_tokens=-1)
    with pytest.raises((BudgetExceeded, AttributeError)):
        provider.complete(request)
    assert ledger.summary()["reserved_usd"] != "0"
    with pytest.raises(BudgetExceeded, match="Unresolved"):
        provider.complete(request)
    assert len(calls) == 1


def test_revoked_environment_budget_stops_existing_provider_before_dispatch(transport, monkeypatch):
    provider, _, request, ledger, calls, _ = transport
    monkeypatch.setenv("API_BUDGET_USD", "0")
    with pytest.raises(BudgetExceeded):
        provider.complete(request)
    assert not calls and ledger.summary()["reserved_usd"] == "0"


def test_configuration_is_snapshot_and_internal_mutation_fails_approval(transport):
    provider, _, request, _, calls, config = transport
    config["model"] = "external mutation"
    provider.complete(request)
    assert calls[0]["model"] == "synthetic-test"
    provider.config["model"] = "internal mutation"
    with pytest.raises(BudgetExceeded, match="configuration"):
        provider.complete(request)
    assert len(calls) == 1


def test_known_usage_is_charged_even_if_response_decoding_fails(transport):
    provider, response, request, ledger, _, _ = transport
    response.choices = []
    with pytest.raises(IndexError):
        provider.complete(request)
    assert ledger.summary()["settled_usd"] == "0.00012"
    assert ledger.summary()["reserved_usd"] == "0"


@pytest.mark.parametrize("failure", [TimeoutError, KeyboardInterrupt])
def test_timeout_or_operator_interrupt_is_never_automatically_refunded(transport, failure):
    provider, _, request, ledger, _, _ = transport

    def timeout(**kwargs):
        raise failure("SYNTHETIC uncertain dispatch interruption")

    provider.client.chat.completions.create = timeout
    with pytest.raises(failure):
        provider.complete(request)
    assert ledger.summary()["reserved_usd"] != "0"
    with pytest.raises(BudgetExceeded, match="Unresolved"):
        ledger.reserve("next", "0.001")
