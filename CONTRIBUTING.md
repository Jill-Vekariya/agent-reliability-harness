# Contributing

Use Python 3.12.14 and the committed uv lock. Run `make setup`, then `make ci` before proposing changes. On Windows, use `TEST_PROJECT.cmd` with Docker Desktop running.

Keep data/provenance, recordings, and expected results reviewable. Never mark AI-authored tasks human-reviewed without actual review. Record aliases, ties, numeric policies, duplicate handling, and expected behavior explicitly.

Changing a model-visible request invalidates its recording. Do not edit a baseline or recording to conceal a regression. Propose an intentional reference change separately with task/config/source hashes and a review rationale. The initial synthetic baseline is an engineering bootstrap, not a human-approved live benchmark.

Do not commit keys, private traces, caches, or fabricated results. Use sanitized reproductions. All live calls need verified pricing and explicit scoped spending approval; default commands remain offline.

The blank benchmark packet is `reviews/benchmark-candidates.json`; copy it for actual review, preserve provenance and dated attestations, and run `arh review-check --packet PATH`. `--require-complete` must fail while reviews are pending. Resolve disagreements through an identified dated adjudication referencing the accepted review hash. Metadata changes require maintainer review; the checker does not promote tasks.

`tasks/development_exposure.json` records public development exposure. Do not remove entries or relabel existing cases to manufacture a holdout. Review the deterministic groups and near-duplicate candidates in `tasks/grouped-split.proposal.json`; genuinely new families are needed for test. Keep packet/proposal provenance current and validate with `make ci`.

For audit evidence, use `scripts/collect_evidence.py --audit --output reports/audit-evidence.json` through the pinned environment. Keep historical release evidence intact. A passing local suite does not establish hosted CI, publication, live-model performance, or completed human participation.
