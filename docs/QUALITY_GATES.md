# Reliability quality gates

These four contributions add dataset integrity validation, paired regression
reporting, adversarial runtime coverage, and dedicated continuous integration.
They do not change the SQL execution policy or assert model accuracy.

## 1. Dataset integrity

Run `uv run python -m agent_reliability.quality dataset tasks.json`.
The input is a JSON array using the existing task fields: `id`, `question`,
`family_id`, and explicit `split` (`dev` or `test`). IDs must be unique.
Question text is compared after case folding and whitespace normalization;
questions and families cannot cross splits. Existing review metadata is
validated when supplied, without inventing or modifying it.

The command checks metadata, not semantic equivalence or dataset provenance.
A clean result does not establish that a task is genuinely held out.
The existing task loader remains responsible for full evaluation-task validation.
For YAML datasets, export the task objects to a JSON array first.

## 2. Paired regression reports

Run:

```bash
uv run python -m agent_reliability.quality compare baseline.json candidate.json
```

Each file contains one normalized record per task:

```json
[{"task_id": "example", "passed": true, "latency_ms": 125.0, "cost_usd": 0.002}]
```

This is an explicit interchange format, not a raw trace format. Export `passed`
from the same grading policy in both runs (for example, behavior grading for
safety tasks and correctness grading for answer tasks). Convert trace cost
strings to numeric USD values. Keep model, configuration, task versions, and
attempt-selection policy fixed; compare repeated samples separately.

Task sets must match exactly. Duplicate task IDs and empty runs fail closed.
The report lists regressions and improvements, absolute pass-rate delta, and
latency/cost totals and deltas. Missing metrics remain null, never zero.
Metrics must be finite and non-negative. Totals are descriptive and do not
perform a statistical significance test or impose latency/cost budgets.

The default gate rejects any net pass-rate drop. `--max-drop 0.05` allows an
absolute five-percentage-point drop. Individual regressions remain visible even
when offset by improvements. Exit codes: 0 passes, 1 exceeds the drop threshold,
2 invalid input. JSON goes to stdout and diagnostics go to stderr.

## 3. Adversarial runtime coverage

`uv run pytest tests/quality/test_adversarial_runtime.py -q` exercises SQL
mutation, attachment, stacked statements, unknown tools, malformed arguments,
foreign result IDs, and fabricated answer rows against the actual runtime and
the repository's sandbox fixture. Rejected SQL is followed by a table-count
check. This targeted suite supplements, rather than replaces, existing sandbox
and recovery tests; a row count alone is not a full database fingerprint.

## 4. Continuous integration

The Reliability quality workflow installs the frozen project environment,
runs lint and type checks for the new module, executes the quality suite on
Python 3.12, and retains JUnit results. It needs no provider credentials and
uses read-only repository permissions. Run the same checks locally:

```bash
uv run ruff check src/agent_reliability/quality.py tests/quality
uv run mypy src/agent_reliability/quality.py
uv run pytest tests/quality -q
```

Use the existing full CI and Docker acceptance workflows for comprehensive
project verification. This workflow tests the gate implementation; actual
baseline/candidate files and held-out datasets must be supplied explicitly.
