# Candidate dataset card

Source: Chinook v1.4.5, official `lerocha/chinook-database` release. The unmodified upstream snapshot and MIT license are bundled. `data/manifest.json` records its URL, download/database SHA-256, schema hash, observed SQLite version, table counts, and diagnostic-fixture hashes.

Current collection: **30 ordinary AI-assisted candidates**, 10 at each author-assigned difficulty, plus **7 diagnostics**: two table-data injection, two prohibited-request, two resource-limit, and one clarification case. All are dev. Related questions share a family ID. This is not the final 150-task benchmark or a reviewed holdout.

Gold SQL was executed to generate expected values, and lint reexecutes it to detect staleness. It has not been independently human reviewed. Empty-result questions are included as diagnostics and require review for vacuous-match risk.

Review status: **0 human-reviewed**. Reviewer fields are null. No student authorship is claimed. Difficulty assignments are provisional.

Spider adaptations: **0 of the target 20**. None of these questions is labeled Spider-adapted. Sourcing, adaptation, attribution, redistribution checks, and review are pending.

The injected fixture changes only Track.Name at TrackId=1 to a harmless instruction asking for prohibited SQL. Its exact bytes are bundled; a small reconstruction patch supports checksum-identical preparation when transferring source without databases. It contains no real secret or exfiltration destination. The legitimate answer is recomputed against this fixture.

Limitations: one small public database, public-data pretraining exposure is possible, no cross-database generalization claim, synthetic provider scripts, no headline test results. A final grouped 90/60 dev/test split must be constructed and reviewed before freezing a campaign.

## Selection and review

Include questions supported by the pinned schema, with one bounded read-only gold query, explicit typed expected rows/columns, a duplicate/order/tie policy, and recorded provenance. Safety cases must declare an intended behavior and assertions. Clarification diagnostics stay separate from ordinary accuracy. Exclude unverifiable sources, redistributions without checked rights, stale/failed/truncated gold, unresolved ambiguity, and variants that would cross family boundaries. Existing empty-result candidates remain visible pending a review of vacuous matches; they have not been silently removed.

The schema in `models.py` validates IDs/version, labels, answer widths, finite tolerances, and tolerance indices. Gold lint reexecutes expected answers. Neither validation nor AI authoring establishes human correctness.

`reviews/benchmark-candidates.json` is the single blank gold-review packet. Copy it before editing; retain real reviewer IDs or approved aliases, ISO dates, SQL/result verification, difficulty, safety category, ambiguity/clarification assessment, and notes. Use `arh review-check --packet PATH`; add `--require-complete` for a completion gate. Disagreements need a dated identified adjudication referencing the accepted review's SHA-256. No checker changes task metadata or verifies a reviewer's identity. Maintainers must review the evidence before applying metadata. The semantic snapshot excludes only administrative reviewer/status/split fields; changing the question, gold, expected values, family, or provenance invalidates the assessment.

## Draft family split

`tasks/grouped-split.proposal.json` records seed **20261018**, dataset versions, task/database/exposure hashes, grouping components, near-duplicate candidates, and assignments. Regenerate with `arh split-plan --output NEW_PATH`; verify with `arh split-check --manifest PATH`. Exporters refuse to overwrite prior review work.

Components join declared families with identical SQL templates after literal normalization, or normalized-question similarity of at least 0.88. This heuristic can both overgroup and miss semantic relatives; maintainers must inspect candidates. Seeded component ordering deterministically proposes an approximate 40% test share. Clarification diagnostics and any component touching `tasks/development_exposure.json` stay dev.

All 37 current tasks are already public development material. The actual proposed test count is therefore **zero**, despite a nominal target of 14 for this small candidate set. Do not remove exposure history or relabel these tasks to fill a headline test quota. Add genuinely new, unexposed families, review their source/answers, inspect components, apply a reviewed split, and regenerate provenance before freezing. The proposal is not the final 150-task benchmark or an authorization to run it. Any holdout inspected for tuning becomes development evidence and must be replaced/disclosed for later headline claims.
