# Milestone evidence and ownership exercises

These exercises are pending student work. AI-generated code is not recorded as a student contribution.

## 1. Agent and sandbox

Command: `.venv/bin/python -m pytest tests/integration -q` (Linux).
Exit 0; 30 passed, 0 failed, 0 skipped at this milestone.

A separate minimal worker applies SQLite policy and OS limits; its parent bounds output and lifetime. Windows users run the Linux container. Native Windows worker execution is intentionally unavailable.

The first test run found COUNT(*) authorization with an empty column and an absent database-name field. The allowlist now handles that SQLite callback shape without allowing additional tables.

Ownership exercise: add a test proving that a destructive statement hidden behind comments is rejected.

Interview questions:
1. Why does a connection lock timeout fail to bound query execution?
2. What remains risky after opening a database read-only?
3. Why must final answers reference results from the current attempt?
