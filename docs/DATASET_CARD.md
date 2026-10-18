# Candidate dataset card

Source: Chinook v1.4.5, official `lerocha/chinook-database` release. The unmodified upstream snapshot and MIT license are bundled. `data/manifest.json` records its URL, download/database SHA-256, schema hash, observed SQLite version, table counts, and diagnostic-fixture hashes.

Current collection: **30 ordinary AI-assisted candidates**, 10 at each author-assigned difficulty, plus **7 diagnostics**: two table-data injection, two prohibited-request, two resource-limit, and one clarification case. All are dev. Related questions share a family ID. This is not the final 150-task benchmark or a reviewed holdout.

Gold SQL was executed to generate expected values, and lint reexecutes it to detect staleness. It has not been independently human reviewed. Empty-result questions are included as diagnostics and require review for vacuous-match risk.

Review status: **0 human-reviewed**. Reviewer fields are null. No student authorship is claimed. Difficulty assignments are provisional.

Spider adaptations: **0 of the target 20**. None of these questions is labeled Spider-adapted. Sourcing, adaptation, attribution, redistribution checks, and review are pending.

The injected fixture changes only Track.Name at TrackId=1 to a harmless instruction asking for prohibited SQL. Its exact bytes are bundled; a small reconstruction patch supports checksum-identical preparation when transferring source without databases. It contains no real secret or exfiltration destination. The legitimate answer is recomputed against this fixture.

Limitations: one small public database, public-data pretraining exposure is possible, no cross-database generalization claim, synthetic provider scripts, no headline test results. A final grouped 90/60 dev/test split must be constructed and reviewed before freezing a campaign.
