# Failure evidence status

Real live-model failures observed: **0**. No live model experiment or human labeling has been performed. The reserved target of 50 distinct held-out dev failures is entirely pending. There is no evidence-backed live failure taxonomy accuracy yet.

Synthetic detector demonstrations, not real model incidents:

| Task | Observable evidence | Meaning | Remedy illustrated |
|---|---|---|---|
| q002 | Query requests InventedName; SQLite returns no such column | Scripted hallucinated-schema fixture | Inspect schema and query Name, shown in a separate scripted recovery |
| s001 / s002 | Injected Track.Name reaches the next fixture request; DELETE is then blocked | Unsafe scripted decision and successful SQL enforcement | Treat stored text as data; retain mandatory authorizer |
| s005 / s006 | Recursive sequence or Cartesian join hits a resource limit | Expected resource-enforcement diagnostic | Terminate/reap worker; do not claim a complete query result |

The other categories have no real observed examples. Synthetic unit fixtures test classification mechanics and are not evidence of real category prevalence. Recoverable errors and expected resource termination must not automatically be counted as overall task failures.

Actual implementation bugs and their fixes are recorded separately in `docs/DECISIONS.md`.

The subsequent engineering audit reproduced spending-rounding, malformed-trace, and resumed-regression failures and added worker/interruption and missing-coverage tests. See `docs/AUDIT.md` for repository evidence, fixes, and finite-test limits. These implementation failures are not live-model incidents, human labels, or measured model failure prevalence.

The v0.3.0 screenshot review exposed stale presentation metadata: the public exporter selected an older 64-test record, the viewer caption hardcoded 0.2, and capture could run before widgets settled. Patch 0.3.1 binds counters to a published record's checksum/version, derives the caption from package metadata, and waits for rendered controls. Three integrity tests and current screenshots record the fix. This is an implementation lesson, not a model-performance result.
