# Evidence report - current release v0.3.1

## A. Implemented

Protected read-only SQL execution and cleanup; typed duplicate-aware grading; exact budget authorization/exposure arithmetic and unknown-charge recovery; bounded schema/hash-checked traces; resumed-regression provenance; atomic JSON snapshots; benchmark review/adjudication forms; development-exposure-aware grouping; frozen experiment gates; planned-attempt coverage; and scoped statistical reporting.

The final presentation patch derives the viewer version from installed package metadata and selects public test counts from a checksum-bound published record. Counts display their release identifier; invalid references and Boolean counts cannot become claims. Browser capture waits for finished rendering and instantaneous scrolling. The original baseline, recordings, candidate answers, and split assignments remain unchanged. [AUDIT.md](AUDIT.md) contains prioritized findings, tests, and limits.

## B. Verified locally

| Execution | Actual result |
|---|---|
| Audited `make ci` and nine-command offline capture | 145 tests passed before the presentation patch; exact outputs/hashes retained in `reports/audit-evidence.json` |
| Focused patch lint/format/types and export/viewer tests | 32 source files type-checked; 8 focused tests passed in Docker with the candidate source mounted |
| Anonymously downloaded v0.3.1 image, `pytest -q -p no:cacheprovider` | **148 passed, zero failures/skips, 61.93 seconds** |
| Same image, `arh eval --all` | 37-case gate passed; 29/30 ordinary scripted matches; zero regressions/incompatibilities |
| Published-image runtime probe | Installed version/source matches checkout; database checksums; UID 10001; read-only root; writable reports; zero effective capabilities; no-new-privileges; loopback-only network; 768 MiB / two CPUs / 64 PIDs; API budget zero |
| Public browser | Four case controls, supported answer, schema failure, blocked SQL, recovery, 375-pixel layout, and displayed **148 / v0.3.1** passed; no browser exceptions/overflow |
| Local published viewer browser | Version **0.3.1**, settled widgets, and regression button passed; health HTTP 200 |
| Final artifact validation | 13 uploaded asset digests matched local bytes; SHA256SUMS and local Markdown links verified |

Current container commands and outputs are in [published-image.json](../reports/releases/0.3.1/published-image.json). [verification.json](../reports/releases/0.3.1/verification.json) links workflow, probe, browser, screenshot, and checksum evidence. These containers used network disabled, read-only root, explicit writable temporary mounts, non-root identity, dropped capabilities, and resource limits. The serving viewer binds only to localhost and is healthy at http://localhost:8501.

The Windows launcher itself was exercised for v0.3.0: 145 tests and the fixed 20-task gate passed. Its unchanged Compose-based image resolution now selects 0.3.1; current 0.3.1 downloaded-image/browser checks are recorded separately. Historical native/Docker records keep their original versions and source hashes.

## C. Verified externally

The [v0.3.1 release](https://github.com/Jill-Vekariya/agent-reliability-harness/releases/tag/v0.3.1), source revision `394f42c2674d1d2135adaf0606f9fc789fef967c`, has release ID **416622415** and 13 checksummed assets. The [receipt](../reports/releases/0.3.1-receipt.json) records actual IDs, sizes, URLs, and GitHub-reported SHA-256 digests.

Successful hosted runs: [patch PR](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152580419), [main/Pages](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152751839), [tag/container](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39152759313), and [public evidence selection](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/39153456023). Native and Docker CI summaries each report 148 tests. Main pins Ubuntu 24.04 and Node 24 checkout/Pages refs; publication uses explicit verification gates.

Published image: `ghcr.io/jill-vekariya/agent-reliability-harness:0.3.1@sha256:4254993a830a5b827300f5c415fcbad4a1aaa4176c0a08130ff55cf02b8004da`. Anonymous inspection/pull passed. SPDX SBOM and SLSA provenance v1 predicates are present in the attestation manifest. The public static walkthrough returned HTTP 200. [PUBLICATION.md](PUBLICATION.md) preserves prior release identities and their distinct scope.

## D. Empirically measured

Fresh real-provider attempts: **0**. Paid API spend: **USD 0**. Human task reviews: **0**. Live-model pass@1/pass@5, retry benefit, cost/latency tradeoffs, ablations, safety rates, and human-classifier agreement remain **not measured**. Synthetic pytest observations validate the pipeline only. Engineering timings and 29/30 scripted matches are not model measurements.

## E. Still blocked

1. Real reviewers must verify gold/results, provenance, ambiguity, difficulty, and safety using `reviews/benchmark-candidates.json`; validation does not establish identity or diligence.
2. All 37 current tasks are development-exposed. Genuine unexposed families, the target reviewed corpus, sourced adaptations/rights checks, and a final grouped holdout remain incomplete.
3. Exact models, official pricing/context bounds, credentials, a scoped nonzero spending approval, and an actual freeze are required before a live pilot. No approval or review has been fabricated.
4. Personal ownership exercises and actual held-out failure labels require the user's participation. Publication is complete and does not substitute for that work.

## F. Remaining risks

Finite tests do not prove complete security. Malicious Python/repository/host/SDK code is outside the SQL boundary. Cleanup cannot survive host death/SIGKILL; atomic replacement does not promise power-loss durability. Trusted hashes need a trusted reference. Live billing/model compatibility is untested. Near-duplicate detection and failure classification are heuristic; public-data contamination remains possible. Few-family intervals can be degenerate. Unknown usage and missing campaign coverage prevent complete cost/performance claims. The public site is a static walkthrough, not a public SQL backend.

## G. Next actions

1. Complete genuine gold/provenance review and personal ownership exercises; add unexposed families and resolve disagreements.
2. Prepare and approve a concretely priced pilot, verify real-provider accounting, and collect fresh planned repetitions with gaps retained.
3. Obtain real failure labels and report supported paired/ablation effects with family uncertainty and explicit denominators.

## H. Assessment

| Dimension | Evidence-based assessment |
|---|---|
| Engineering | Stronger failure handling, provenance, coverage, and evidence display; 148 tests support the implemented paths. |
| Security validation | Broad adversarial SQL/worker/accounting/trace/reference tests and actual container probes; finite scoped protection. |
| Benchmark quality | Review/leakage tooling is prepared; actual review and a clean holdout remain the largest gap. |
| Empirical evidence | Absent for live models; no accuracy, savings, or ablation conclusion is justified. |
| Reproducibility | Pinned runtime/data/dependencies, preserved references, campaign hashes, immutable image, and checked artifacts; platform/live nondeterminism remains. |
| Public delivery | v0.3.1 source, CI/Pages, GHCR image, anonymous download tests, and current browser checks are evidenced. |
| Interview readiness | Factual resume bullets, a demo route, code-linked answers, real implementation failure cases, and ownership exercises are ready; personal understanding still needs practice. |
