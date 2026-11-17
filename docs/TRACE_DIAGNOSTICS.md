# Offline trace diagnostics

Summarize saved traces without a model API key or database connection:

```bash
uv run python -m agent_reliability.diagnostics reports/traces/*.json
```

Pass individual schema-version-1 trace JSON files, not a run registry or an
array of traces. The command reads files without changing them. It reports:

- Trace counts grouped by termination label.
- SQL result, failure, policy-block, resource-limit, and truncation counts.
- Infrastructure-error count without copying error messages.
- Nearest-rank p50/p95 and maximum end-to-end trace latency.
- Decimal USD total only when every input trace records its cost.

SQL, database rows, provider messages, event payloads, task IDs and attempt IDs
are omitted from the report. Termination labels are retained verbatim; inspect
custom labels before publishing a report. Input-validation errors can include
local file paths. This is an operational summary, not a trace redaction tool,
a full schema validator, or an answer-quality grade.

## CI budgets

```bash
uv run python -m agent_reliability.diagnostics reports/traces/*.json \
  --max-p95-ms 2000 --max-cost-usd 0.50 --fail-on-error > diagnostics.json
```

Latency budgets are in milliseconds; cost is the total USD across input traces.
A value exactly equal to a budget passes. If a cost budget is requested but any
trace has unknown cost, the gate fails rather than treating unknown cost as zero.
`--fail-on-error` rejects recorded SQL failures or infrastructure errors. A
blocked unsafe SQL proposal is counted as a failed SQL result; omit this flag
when inspecting expected safety-test failures. Truncation alone does not fail
this flag. Termination labels are counted but do not independently fail it.

Exit codes: 0 passes, 1 violates a requested gate, 2 has invalid input. Reports
are JSON on stdout; invalid-input diagnostics use stderr. Duplicate task/attempt
pairs, unsupported schema versions, invalid booleans, and negative/non-finite
latencies or costs are rejected. No statistical significance claim is made.

Run focused tests with:

```bash
uv run pytest tests/unit/test_trace_diagnostics.py -q
```
