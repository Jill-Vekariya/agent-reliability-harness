# Delivery status

R0 offline engineering release is implemented and verified locally and inside Docker on the connected Windows computer. The local viewer is running at http://localhost:8501. Source is installed under C:\Users\jillv\Projects\AgentReliabilityHarness. This is not a public hosted deployment.

Verification: 60 tests passed; zero failures/skips. Nine native release checks exited 0. The final Docker suite passed 60 tests in 39.84 seconds with networking disabled; the 20-task current-tool regression gate passed. Browser navigation and the regression button were exercised. Screenshots are bundled. See the JSON evidence for commands, versions, hashes, and actual outputs.

API spend: USD 0. Fresh live model runs: 0. Human task reviews: 0.

R1 pending: review the existing candidates; expand 30 ordinary candidates toward 120, including 20 properly sourced Spider adaptations; expand six safety candidates toward 30; keep the additional clarification diagnostic separate; construct the grouped holdout and freeze it. All current cases are dev candidates.

R2 pending: approve an explicitly priced pilot/study, collect fresh repetitions, obtain actual held-out human failure labels, and generate the empirical comparisons/ablations/safety analysis. No empirical performance or student contribution has been invented.

The 0.2.0 public-delivery update adds four export safety/evidence tests (64 engineering tests total in the latest native evidence), a static browser walkthrough, CI-gated Pages deployment, tagged GHCR publishing, a prebuilt-image Compose path, and interview/resume preparation. All nine native checks passed for this update; see `reports/release-evidence.json`.

The public repository is https://github.com/Jill-Vekariya/agent-reliability-harness. Hosted CI, container digests, and deployment results must be checked in the actual Actions runs/release notes. The public static walkthrough executes no SQL or model calls; the full execution demo runs in Docker. A public hosted SQL backend remains out of scope for this zero-cost release.
