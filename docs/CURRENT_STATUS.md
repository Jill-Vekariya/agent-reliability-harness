# Current status

Updated 2026-10-23 for the cleanup review. This is a software portfolio, with a working offline SQL-worker workflow and a public saved-trace walkthrough. [Release evidence](STATUS.md) retains the actual v0.3.1 observations; its 148-test count is not automatically the count at a newer source revision.

## Run and verify

Use the root README's locked Python or Docker setup. `make ci` checks the source; `arh eval --all` exercises the 37 development cases. The intentional q002 mismatch remains visible and is not a model-accuracy estimate. `python scripts/check_links.py` checks local Markdown paths and anchors; add `--online` for a current external reachability report.

## Remaining work

Real-provider compatibility, live pass@k/cost experiments, human gold review and a genuinely unexposed holdout are unfinished. Zero real reviews and zero fresh provider attempts must not become completed claims. Planned corpus expansion and Spider adaptations require real source/rights review. Core OpenTelemetry mapping does not imply separate GenAI convention compliance.

Personal exercises in [ownership](OWNERSHIP.md) require actual work by the owner. No new research, paid calls or production-scale capability is claimed by this cleanup. Existing limitations in [the threat model](THREAT_MODEL.md) remain applicable.

[Cleanup changes and local verification](CLEANUP_VERIFICATION.md).
