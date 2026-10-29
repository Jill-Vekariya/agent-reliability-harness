# Stage 3 — engineering measurement verified; model-quality review blocked

1. **Outcome.** Implemented and executed a reproducible synthetic workflow study.
   The original 72-job run FAILED and remains retained. A separately predeclared
   amended run VERIFIED all six batches and 72 planned jobs. Model-quality claims
   remain BLOCKED by independent review and genuinely unexposed task families.

2. **Scope and exact source.** Harness only, branch
   `feat/workflow-measurement-stage3`, based on Stage 1 revision
   `bfd4d6f951a6e3d8e3d503cb96c6662ee0e258c6`. Changes remain uncommitted and
   unpublished. Both Docker measurements executed runtime source SHA-256
   `3d983c1a64db49f195057e9e77bb7f93000fb70b7f244b7eaad057a62a5fc4df`
   with dependency-lock SHA-256
   `7c09de1294c24df100289f25a260375bf56a77868e1794e11793a8c2b4700997`.
   Individual driver/protocol/source manifests and final patch hashes accompany
   the package. The first run used the explicitly recorded cached-runtime image;
   the amended run used the completed normal Dockerfile build. Installed runtime
   bytes were checked against checkout bytes before admission.

3. **Evidence and results.** Linux Docker, Python 3.12.14, PostgreSQL 16.15;
   two workers, three attempts, 10-second attempt and 45-second job deadlines.
   The measurement container had limits of 2 CPUs, 768 MiB and 64 PIDs; PostgreSQL
   separately had 1 CPU/512 MiB. Seeds: 17, 29, 41, with matched ordering and
   alternating arm order. One worker was actually SIGKILLed after the effect
   sink's first invocation in each amended fault batch. Approvals were issued
   by the disclosed automated synthetic driver, not an independent human.

   | Run | Planned / terminal jobs | Succeeded | Failed | Cancelled | Label |
   |---|---:|---:|---:|---:|---|
   | Initial | 72 / 72 | 33 | 33 | 6 | FAILED: timing/fault criteria missed |
   | Amended | 72 / 72 | 54 | 12 | 6 | VERIFIED: all declared invariants held |

   The amended run's 12 failures were intentional: six retry-exhaustion cases
   and six missing-price refusals. They remain in all planned-job denominators.

   | Seed | No-fault median terminal latency | Worker-loss median terminal latency | Observed recovery |
   |---|---:|---:|---:|
   | 17 | 11.780 s | 11.745 s | 5.758 s |
   | 29 | 11.208 s | 11.649 s | 3.556 s |
   | 41 | 8.225 s | 8.529 s | 3.968 s |

   The amended run retained **87 attempts**, including three lost attempts;
   six logical effects had nine sink invocations and **zero duplicate committed
   logical effects**. This verifies the synthetic sink's deduplication mechanism,
   not exactly-once effects for external services. All 54 cross-tenant probes
   returned the expected denial or empty scoped list. Budget conservation had
   zero discrepancies: 72 known synthetic credits settled, with 60 credits held
   for unknown usage. Uncertain zero-cost effect operations were also preserved.

   The mean paired difference in batch median terminal latency was +0.237 seconds.
   The exploratory 2,000-resample batch-bootstrap interval was [-0.035, +0.441]
   seconds (seed 1729). It includes zero and is inconclusive. Three batch pairs
   on one shared host support no population, production-availability or general
   throughput claim. Child user CPU ranged 33.72–44.90 CPU-seconds per batch;
   observed maximum reaped-child RSS ranged 66.5–75.3 MiB. That RSS statistic is
   cumulative per-process peak accounting, not simultaneous/container memory.

   Commands were `python scripts/measure_workflow.py --source-context
   /run/source-context.json --output /reports/stage3/measurement-001` (exit 1),
   then the same command with output `measurement-002` and the v2 protocol/driver
   mounts (exit 0). Receipts include the exact selected protocol and script hashes,
   arm results, queue waits, terminal latency coverage, operations, worker logs,
   sanitized attempts/results and independent SQLite sinks.

   Local final gate: **186 passed, 33 explicitly skipped**, Ruff/format, Mypy
   (42 files), task validation, review/split checks and offline regression passed.
   Its verifier correctly exited 2 because native PostgreSQL was not configured
   in that scratch environment. Separately, Docker ran the 33 real PostgreSQL
   cases plus 31 workflow-unit cases: **64 passed**, exit 0.
   The final native closure retained 186 passes and 33 explicit database skips.
   A supplemental native CLI check hit SQL wall deadlines; it remains retained.
   After pinning CLI root selection to the inspected checkout, explicit-root
   validation/regression passed with the same SQL limits. Both commands also
   passed in network-disabled containers on the verified Docker image.

   Final normal-image full suite: **214 passed, zero failures/errors/skips**.
   Final API smoke verified health, authenticated access, anonymous denial, a real
   fixture result and duplicate-submission identity. Task-owned containers were
   removed while both data volumes were retained. The [resumed Stage 2 report](../stage2/RESUMED.md)
   records the three preceding failed full suites and their fixes. The last read
   after API restart now uses the existing bounded reconnect observation helper;
   per-request and total limits and correctness assertions remain intact.

4. **Changes and trade-offs.** Added a protocol-bound measurement driver, source
   context exporter, explicit denominator/uncertain-cost tests and current review
   packet. The first driver admitted jobs and ran access probes before starting
   workers, spending part of the job deadlines on driver delay. The amended
   protocol starts workers during admission, gives synthetic approvals promptly,
   fixes the effect probe last and moves access probes after the timed workload.
   It retains the same deadlines/resource/stopping limits. The default build
   finished and idle verification services were paused before the amended run;
   run-to-run differences cannot isolate one causal driver improvement.

5. **Failures, blockers and unverified claims.** All failed batches, timeouts,
   earlier failed builds and full-suite failures are retained. Windows checkout
   line endings changed checksum-bound JSON assets: restoration was allowed only
   where normalized bytes exactly equalled the committed Git blob (207 files;
   changed YAML files were preserved). `.gitattributes` now pins evidence formats
   to LF; recorded checksums were not changed. A further Docker test exposed the
   missing writable offline-artifact setting; the workflow image now directs
   output to `/reports/artifacts` while keeping its root read-only. No test
   assertion or SQL safety boundary was weakened.

   All 37 existing tasks remain development-exposed, zero independently attested
   labels, zero eligible validation tasks and zero genuinely unexposed test tasks.
   Use `reviews/stage3-review-packet.json` for current review; archived packets bind
   their original byte-level manifests. Live provider use, model uplift, CI for
   this unpublished branch, public backend and production usage are UNVERIFIED
   or NOT APPLICABLE (no live calls/spending/publication performed).

6. **Personal learning/contribution.** Explain the driver confound, why 72 jobs
   are only three matched batch pairs per comparison, how the sink differs from
   exactly-once delivery, and why unknown costs remain reserved. Independently
   add a declared container memory/CPU sampling protocol, preserve missed samples,
   and justify measurement overhead. No independent user implementation or human
   label review is claimed; existing AI-assistance disclosures remain intact.

7. **Proposed next stage.** Stage 4: inspect the four other current repositories,
   choose changes from demonstrated limitations, and preserve negative results.
   Human label review/new unseen task families can proceed independently. A live
   model pilot, pushing/merging, public deployment, licensing changes or spending
   still needs its specific authorization. No such action was performed here.
