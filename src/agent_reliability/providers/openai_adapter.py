"""One live adapter. Construction and each request fail closed without matching approval."""

import json
import os
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..models import ProviderReply, ToolCall
from ..util import canonical, digest
from .budget import BudgetExceeded, Ledger, cap_micros, usd


def priced_usd(pricing: dict[str, Any], prompt: int, cached: int, completion: int) -> str:
    # Multiplying a per-million price by tokens gives microdollars directly.
    # Rational arithmetic avoids Decimal-context rounding near a microdollar boundary.
    exposure = (
        (prompt - cached) * Fraction(Decimal(str(pricing["input_usd_per_million"])))
        + cached * Fraction(Decimal(str(pricing["cached_input_usd_per_million"])))
        + completion * Fraction(Decimal(str(pricing["output_usd_per_million"])))
    )
    amount = -(-exposure.numerator // exposure.denominator)
    return usd(amount)


def validate_approval(approval: dict[str, Any], config: dict[str, Any], tasks_hash: str) -> None:
    required = [
        "approved_by",
        "approved_at",
        "campaign_id",
        "official_pricing_url",
        "pricing_checked_at",
        "official_context_limit_url",
    ]
    if any(not approval.get(key) for key in required):
        raise BudgetExceeded(
            "Complete explicit approval and verified pricing/context metadata required"
        )
    if approval.get("config_hash") != digest(config) or approval.get("task_hash") != tasks_hash:
        raise BudgetExceeded("Approval does not match configuration or task corpus")
    if approval.get("model") != config.get("model") or approval.get("provider") != "openai":
        raise BudgetExceeded("Provider/model scope mismatch")
    budget = Decimal(str(approval.get("budget_usd", "0")))
    if not budget.is_finite() or budget <= 0:
        raise BudgetExceeded("Paid execution disabled: authorized budget is zero")
    for key in ("input_usd_per_million", "cached_input_usd_per_million", "output_usd_per_million"):
        value = Decimal(str(approval.get(key, "NaN")))
        if not value.is_finite() or value < 0:
            raise BudgetExceeded("Unknown or invalid pricing")
    context = approval.get("provider_context_window_tokens", 0)
    if type(context) is not int or context <= 0:
        raise BudgetExceeded("A verified full provider context-window upper bound is required")
    for name, default in (("max_output_tokens", 512), ("max_input_tokens", 8192)):
        limit = config.get(name, default)
        if type(limit) is not int or limit <= 0:
            raise BudgetExceeded(f"{name} must be a positive integer")
    if Decimal(str(approval["cached_input_usd_per_million"])) > Decimal(
        str(approval["input_usd_per_million"])
    ):
        raise BudgetExceeded(
            "Reservation assumes cached-input price does not exceed full input price"
        )


class OpenAIProvider:
    origin = "live"

    def __init__(
        self,
        approval: dict[str, Any],
        config: dict[str, Any],
        tasks_hash: str,
        ledger: Ledger,
        task_key: str,
        client: Any = None,
    ) -> None:
        validate_approval(approval, config, tasks_hash)
        self.approval, self.config = deepcopy(approval), deepcopy(config)
        self.ledger, self.task_key, self.tasks_hash = ledger, task_key, tasks_hash
        self._check_scope()
        if client is None:
            from openai import OpenAI

            self.client: Any = OpenAI(max_retries=0, timeout=30.0)
        else:
            self.client = client

    def _check_scope(self) -> None:
        validate_approval(self.approval, self.config, self.tasks_hash)
        try:
            environment_cap = cap_micros(os.environ.get("API_BUDGET_USD", "0"))
        except (ValueError, InvalidOperation) as exc:
            raise BudgetExceeded("Invalid API_BUDGET_USD") from exc
        if environment_cap <= 0 or self.ledger.cap > environment_cap:
            raise BudgetExceeded("API_BUDGET_USD must explicitly cover the authorized ledger cap")
        if self.ledger.cap > cap_micros(str(self.approval["budget_usd"])):
            raise BudgetExceeded("Ledger cap exceeds approved cumulative cap")

    def complete(self, request: dict[str, Any]) -> ProviderReply:
        self._check_scope()
        if request["model"] != self.config["model"]:
            raise BudgetExceeded("Request model changed after approval")
        output_cap = int(self.config.get("max_output_tokens", 512))
        if request["max_completion_tokens"] != output_cap:
            raise BudgetExceeded("Output token cap changed after approval")
        input_cap = int(self.config.get("max_input_tokens", 8192))
        # Conservative local admission bound; reserve the FULL verified provider context,
        # not this heuristic, so SDK/tool-template overhead cannot underreserve money.
        if len(canonical(request).encode()) * 2 + 2048 > input_cap:
            raise BudgetExceeded("Conservative input admission cap exceeded")
        pricing = self.approval
        context_cap = int(pricing["provider_context_window_tokens"])
        upper = priced_usd(pricing, context_cap, 0, output_cap)
        key = self.ledger.reserve(self.task_key, upper)
        try:
            response = self.client.chat.completions.create(
                **request,
                parallel_tool_calls=False,
                n=1,
                stream=False,
            )
            usage = response.usage
            if usage is None:
                raise BudgetExceeded("Missing provider usage; charge remains reserved")
            prompt, completion = usage.prompt_tokens, usage.completion_tokens
            details = usage.prompt_tokens_details
            cached = details.cached_tokens if details and details.cached_tokens is not None else 0
            if (
                any(type(value) is not int for value in (prompt, completion, cached))
                or not (0 <= cached <= prompt <= context_cap)
                or not (0 <= completion <= output_cap)
            ):
                raise BudgetExceeded("Usage outside verified billing bounds")
            actual = priced_usd(pricing, prompt, cached, completion)
        except BaseException:
            # An operator interrupt after dispatch is uncertain billing too.
            self.ledger.reconcile(key, None)
            raise
        self.ledger.reconcile(key, str(actual))
        choice = response.choices[0]
        calls = []
        for call in choice.message.tool_calls or []:
            try:
                args = json.loads(call.function.arguments)
                if not isinstance(args, dict):
                    args = {"_malformed": "Arguments must be an object"}
            except (ValueError, TypeError):
                args = {"_malformed": "Invalid JSON arguments"}
            calls.append(ToolCall(name=call.function.name, arguments=args))
        return ProviderReply(
            calls=calls,
            content=choice.message.content,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cached_input_tokens=cached,
            model=response.model,
            finish_reason=choice.finish_reason,
            cost_usd=str(actual),
        )


def read_approval(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BudgetExceeded("Approval file is missing; no paid request was made")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise BudgetExceeded("Approval must be a JSON object")
    return value
