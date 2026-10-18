# Contributing

Use Python 3.12.14 and the committed uv lock. Run `make setup`, then `make ci` before proposing changes. On Windows, use `TEST_PROJECT.cmd` with Docker Desktop running.

Keep data/provenance, recordings, and expected results reviewable. Never mark AI-authored tasks human-reviewed without actual review. Record aliases, ties, numeric policies, duplicate handling, and expected behavior explicitly.

Changing a model-visible request invalidates its recording. Do not edit a baseline or recording to conceal a regression. Propose an intentional reference change separately with task/config/source hashes and a review rationale. The initial synthetic baseline is an engineering bootstrap, not a human-approved live benchmark.

Do not commit keys, private traces, caches, or fabricated results. Use sanitized reproductions. All live calls need verified pricing and explicit scoped spending approval; default commands remain offline.
