# Evidence report — 0.3.0 publication and audit

## Current verified delivery: v0.3.0

The audit is now published through merged PR #9. Hosted PR, main/Pages, and tag/container workflows succeeded at release revision `2e0d20e36a5c507f951d2de1b63cab62d7e6007f`. The actual GHCR image passed 145 tests in 67.64 seconds, the 37-case offline gate (29/30 ordinary scripted matches), an anonymous inspection/pull, installed-source/checksum checks, and the documented non-root/read-only/network/resource probes. SPDX SBOM and SLSA provenance predicates are present.

Current image: `ghcr.io/jill-vekariya/agent-reliability-harness:0.3.0@sha256:15b7c4c6ea5c73cdb38eab5a06c3aa82d8bb13e3dfb3ae86bceafcfb7bf15e5d`. The Windows launcher passed 145 tests in 59.16 seconds and the fixed regression. Public/mobile and local regression-button browser checks passed; the local viewer now runs the pinned 0.3.0 image at http://localhost:8501. Follow-up PR #10 and main run 39150428931 verified the Ubuntu 24.04 and Node 24 checkout/Pages maintenance.

See `reports/releases/0.3.0/verification.json`, companion command outputs/screenshots, and `SHA256SUMS`. Pre-release audit evidence below keeps its original revision and source hash; package version metadata changed for 0.3.0 and is separately verified in the published-image probe. Human review, genuine held-out tasks, live model calls, and paid spend remain zero.

## A. Implemented

On `audit/hardening-review`: exact cap/exposure rounding and failure accounting; request-time approval checks; bounded trace parsing and trusted replay; atomic JSON replacement; parent deadlines covering blocked input; resumed-regression provenance; stricter task contracts; blank review/adjudication forms; deterministic exposure-aware splits; stronger headline freezes; planned-attempt checkpoints; per-configuration metrics with missing coverage; and a digest-pinned published-image configuration. See `AUDIT.md` for prioritized findings/tests.

The baseline, reference recordings, task YAML, and original split assignments were not changed. Candidate reviews remain pending. These changes shipped in v0.3.0; the original audit checkpoint is retained below.

## B. Verified locally

`reports/audit-evidence.json` records exact commands, timestamps, stdout/stderr, expected/actual exit codes, environment, hashes, and counts:

| Command | Actual result |
|---|---|
| `uv lock --check --offline` | Exit 0; dependency lock consistent |
| `make ci` | Exit 0; lint/format/types, **145 tests passed**, task/review/split checks, 20-task regression |
| `uv run --no-sync arh eval --all` | Exit 0; 37 synthetic current-tool cases, 29/30 ordinary matches, no regressions/incompatibilities |
| `uv run --no-sync arh eval --mode fixture --all` | Exit 0; 37 scripted cases, 29/30 ordinary matches |
| `make eval MODE=replay` | Exit 0; 20 exact saved cases, 19 ordinary matches |
| `arh review-check --packet reviews/benchmark-candidates.json --require-complete` | Expected exit **1**: 0 review attestations, 37 pending |
| `make estimate`, `make report`, `make public-demo` | Exit 0; unavailable prices/results remain unavailable |

Docker audit verification is recorded separately in `reports/audit-desktop.json`: **145 passed in 50.72 seconds**, all 37 regression cases passed the gate (29/30 ordinary scripted matches, zero regressions/incompatibilities), and identity/review/split checks exited 0. Commands used `--network none`, read-only root, temporary writable `/tmp` and `/reports`, 768 MiB, two CPUs, 64 PIDs, dropped capabilities, and no-new-privileges. Runtime identity was `10001:10001`.

The local image `agent-reliability-harness:audit-local` has ID `sha256:d83c48c6ae9c2e01b1123aee4804e6b49d5e4d8f01ad7e4294438592a7c47299` and contains runtime commit `b876150e54fc037403f124d2486722f4ff233bc2`. It was built in `C:\Users\jillv\Projects\AgentReliabilityHarnessAudit`; at that checkpoint the viewer remained on v0.2.1. The audit source hashes matched then; v0.3.0 package metadata and the published viewer are separately verified above.

At the audit checkpoint, an in-container probe also confirmed the same source/lock/task/database/split hashes as native, Python 3.12.14, SQLite 3.46.1, user 10001, zero effective capabilities, no-new-privileges, read-only root, writable reports, loopback-only network interfaces, and the exact 768 MiB / two CPU / 64 PID cgroup limits. Its assertions and environment are saved in the Docker evidence. This verifies the selected runtime controls, not kernel isolation or production readiness.

## C. Verified externally

Read-only checks in `reports/audit-external.json` confirm **existing v0.2.1**, from `d3eb1e0`: main workflow `39129538947` and tag workflow `39129542108` succeeded; the tag's verify/container jobs succeeded and Pages was correctly skipped. The public walkthrough returned HTTP 200. Release ID `416455012` contains actual evidence assets and SHA-256 digests. The released viewer was healthy.

Published index: `sha256:f9eb1a7412e5830fea9ec46c88f33de2410f4953f4ba1bf3bfe88858cda835f8`. See `PUBLICATION.md` for URLs. The released suite had 64 tests. This historical checkpoint did not include audit publication; the authorized v0.3.0 delivery above supersedes that delivery status.

## D. Empirically measured

Fresh real provider attempts: **0**. Paid API spend: **USD 0**. Human task reviews: **0**. Live-model pass@1/pass@5, retry benefit, cost/latency comparisons, ablations, safety rates, and human-classifier agreement: **not measured**. Synthetic pytest observations validate the pipeline only. Test timings are not model latencies.

## E. Still blocked

1. Actual reviewers must verify SQL/results, ambiguity, difficulty, safety, and provenance using `reviews/benchmark-candidates.json`. Validation checks attestations, not identities.
2. All 37 tasks are development-exposed; a clean holdout needs genuinely new families. The target 150-task corpus, 20 sourced Spider adaptations, licenses/review, and final grouping remain incomplete.
3. Exact models, official prices/context bounds, credentials, scoped user approval, and a nonzero cap are required before a pilot. No active approval/freeze was fabricated.
4. Personal ownership exercises and actual held-out failure labels remain uncompleted. Publication is complete; it does not authorize paid-model spending or substitute for human review.

## F. Remaining risks

Finite SQL tests do not prove complete security; malicious Python/repository/host/SDK code is outside the boundary. Cleanup cannot survive host death/SIGKILL. Atomic replacement does not promise power-loss durability. Exact replay rejects changed model-visible behavior. Self-hashes require a trusted reference. Live billing/model compatibility is untested. Near-duplicate detection is heuristic; public-data contamination remains possible. Small-family intervals can be degenerate. Unknown usage and missing coverage prevent complete cost/performance claims. The public walkthrough is static, with no SQL backend.

## G. Next actions, ranked

1. Complete genuine gold/provenance review and add unexposed families; resolve disagreements before freezing a benchmark.
2. Obtain a priced, scoped pilot approval and credentials; verify live accounting, then collect fresh planned repetitions with operational gaps retained.
3. After an approved pilot, collect genuine failure labels and fresh paired repetitions, then report the supported ablation effects and uncertainty.

## H. Assessment

| Dimension | Evidence-based assessment |
|---|---|
| Engineering | Stronger failure handling, provenance, and coverage; tests support implemented paths. |
| Security validation | Broader adversarial SQL/worker/accounting/trace checks; scoped protections, no complete-security claim. |
| Benchmark quality | Better contracts and review/leakage tooling; genuine review and a clean holdout remain the largest gap. |
| Empirical evidence | Absent for live models; no accuracy, savings, or ablation conclusion is justified. |
| Reproducibility | Pinned runtime/data/dependencies, preserved references, explicit plans/hashes; platform/live nondeterminism remains. |
| Public delivery | v0.3.0 source, hosted CI/Pages, GHCR image, and downloaded-image/browser checks are externally evidenced. |
| Interview readiness | Concrete failure cases and exercises prepared; personal understanding/contributions require practice and evidence. |
