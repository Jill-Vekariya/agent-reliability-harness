# Actual decisions

* Python 3.12.14: available in the build environment and pinned in Docker and `.python-version`. The installed SQLite version is recorded separately.
* Standard-library SQLite in a fresh `-I -S` worker: a read-only connection alone cannot bound query CPU, memory, or tool output. SQL is never executed with a provider key in the child environment.
* Docker/Linux as the Windows execution path: Windows pipes and OS resource APIs differ. The project does not quietly weaken the native worker to make a demo launch. Docker Desktop was started and its Linux engine became available through Desktop Commander.
* Typed multisets with augmenting-path matching: sorting or greedy tolerance matching can lose duplicates or reject a valid assignment.
* A fixed 20-case synthetic regression reference: no live recordings exist. An intentionally invented column in q002 tests failure handling, not a real model's quality.
* Exact replay and current-tool regression are distinct. Changed model-visible results invalidate subsequent recorded responses rather than silently replaying incompatible answers.
* An atomic SQLite spending ledger reserves the full verified provider context-window exposure. This is deliberately conservative and can make a pilot uneconomical; a tighter tokenizer-based estimator would need separate validation before relaxing it.
* No headline chart from synthetic outputs. Live results, reviewed tasks, and human agreement remain pending.
* Core OpenTelemetry SDK spans are tested. GenAI-specific semantic-convention compliance is not claimed; exported historical timing is stored as an attribute and export span timing is separate.

## Actual issues found during implementation

1. COUNT(*) reported an approved-table read with an empty column and no database name. An overly strict authorizer rejected it. The policy now accepts this callback shape while keeping the approved-table check.
2. The environment sampled only 1% of OpenTelemetry spans. A local archival exporter now explicitly uses an always-on sampler so representative-export tests do not randomly disappear.
3. A forged final answer containing a JSON Boolean could compare equal to a stored Python integer. Canonical typed JSON now checks final-answer support before grading.

These are implementation findings, not observed live-model failure rates.
