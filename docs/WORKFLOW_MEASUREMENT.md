# Stage 3: bounded synthetic reliability measurement

The predeclared protocol is `experiments/workflow-stage3.v2.protocol.json` (the initial protocol remains
`experiments/workflow-stage3.protocol.json`). It is
recorded with its SHA-256 before any jobs are admitted. This is an engineering
reliability demonstration, not a live model experiment or production benchmark.

The hypothesis is that one worker loss increases attempts and recovery latency
while preserving terminal records, tenant isolation, synthetic-effect deduplication
and budget accounting. Each fresh schema is one experimental batch. Twelve jobs
share two workers, so job outcomes and latencies within a batch are dependent.
Three seed-matched pairs compare `no_fault` with `worker_loss`; arm order alternates
between pairs, and the job order is shuffled identically within each pair.

Every batch includes correct and intentionally incorrect SQL fixtures, a retried
failure, retry exhaustion, queued cancellation, one synthetic effect, two fake
provider calls with known usage, unknown usage, and unknown pricing. The predicted
execution states are nine successes, two intentional failures and one cancelled
job. A workflow success remains distinct from a correct SQL answer. In the current driver, the queued-cancellation control is admitted first, workers
start before the other jobs are admitted, and the synthetic effect is admitted
last so its fault window is observable. Test approvals are immediate, and access
probes run after the timed workload. The fault arm
kills the actual worker process only after its synthetic effect has committed,
then restarts that worker and waits for the ordinary lease expiry/recovery path.
The adapter's logical-effect deduplication is measured independently of attempts.

No human approval is fabricated. The deterministic driver acts as an explicitly
automated test approver for its known synthetic actions. This measures persistence
and consumption, not human decision quality or real approval latency.

## Run and retained output

Use the locked workflow environment in a Linux checks container or equivalent
bounded environment. Supply a **dedicated test database**, never a production or
another project's database. No live-provider key or billable call is used.

```bash
uv run --no-sync python scripts/measure_workflow.py \
  --protocol experiments/workflow-stage3.v2.protocol.json \
  --output .local/stage3/measurement-001
```

For a container without Git, first export host provenance from the exact checkout:

```bash
python scripts/workflow_source_context.py --output .local/stage3/context-001.json
# Build the current source image, then pass the nonsecret context read-only:
docker compose --env-file .env.workflow -f compose.workflow.yaml -p arh-stage3-demo run --rm \
  --volume "$PWD/.local/stage3/context-001.json:/run/source-context.json:ro" \
  checks python scripts/measure_workflow.py --source-context /run/source-context.json \
  --output /reports/stage3/measurement-001
```

The driver checks runtime source, dependency lock, driver and protocol hashes
against the host context, and checks installed runtime files against the source
checkout. A mismatch stops execution. The context is operator-supplied evidence,
not an independently signed attestation. Windows uses equivalent absolute paths.

`ARH_WORKFLOW_TEST_DATABASE_URL` is read only from the environment and never
written to a receipt. Every batch creates and retains its own uniquely named
schema. Existing databases, schemas and records are not cleared. A new output
path is mandatory. Missing PostgreSQL produces a BLOCKED receipt and exit 2.

Limits are two workers, three attempts, ten seconds per attempt, 45 seconds per
job, 60 seconds per batch and 480 seconds for the overall admission schedule.
The Compose checks environment limits the container to 2 CPUs, 768 MiB and 64
PIDs. Run only one measurement container at once. These are synthetic credits,
not authorization to spend money. All spawned worker processes are reaped on
success, failure or timeout; database schemas and evidence remain.

The receipt records all 72 planned jobs, admitted and never-admitted work,
nonterminal jobs, intentional failures, timeouts, attempts, recovery latency,
queue waits, terminal latencies, grade outcomes, tenant checks and budget
conservation. It retains worker logs, sanitized result/attempt records, operation
records and the independent SQLite effect sink. Unknown costs stay reserved.
A batch that misses its fault window is failed, not silently rerun or substituted.

CPU and RSS observations use process resource accounting. Peak child RSS is the
maximum observed for a reaped child so far, not simultaneous/container memory.
Queue and terminal latency summaries report coverage; never-started or unresolved
jobs remain in coverage denominators and receive no fabricated latency values.
All terminal states contribute to terminal-latency summaries, including failures
and cancellations. A successful-run-only chart is not an acceptable substitute.

The arm comparison pairs batches by seed. An incomplete or failed pair suppresses
the paired latency effect rather than dropping the failed sample. With three
complete pairs, a seeded 2,000-resample batch bootstrap is exploratory and coarse;
it supports no production availability, general throughput or population claim.
Every batch and its invariant checks should be inspected before interpreting it.

## Evaluation and independent review

Each measurement output contains a fresh blank, provenance-bound task review
packet using the existing review implementation. The packet includes proposed
SQL and expected outcomes, database checksums, reviewer fields and adjudications.
AI-proposed labels remain pending until independent reviewers actually assess
and record them. The tool does not invent reviewer identities or acceptance.

The current corpus has **37 development-exposed tasks**, zero eligible validation
tasks and zero genuinely unexposed test tasks. Existing exposure history is
preserved. Neither shuffling these tasks nor creating another copy makes them
unseen. New task families need documented provenance, independent review,
maintainer-approved group assignments and the existing freeze checks before any
headline test-set or model-quality comparison is possible.

Model quality, unsafe agent proposals and enforced SQL execution safety remain
separate outcomes. Existing offline regression traces keep blocked unsafe
proposals visible. Their safety checks do not establish that a live model will
avoid unsafe proposals. A live pilot still requires exact models, verified
current prices, a separately approved budget and stopping rules.

## Interview exercise

Explain why there are three batch pairs rather than 72 independent samples,
what the synthetic sink proves, and why uncertain costs remain reserved. Review
one failed batch before examining averages. As independent work, add a recorded
container memory/CPU time series with a declared sampling interval and explain
how missed samples and measurement overhead affect the conclusions. Do not claim
that this exercise or any independent implementation has already been completed.

## Retained initial failure and amended protocol

The initial run admitted all jobs and completed access probes before starting
workers. Job deadlines were already running during that driver delay. Its six
batches and 72 planned jobs are retained as a failed measurement, with the exact
initial driver source and protocol. Several jobs timed out and fault recovery
was not established in the required windows; no paired latency effect is claimed.

The amended protocol was written before a separate run. It starts workers during
admission, grants synthetic approvals promptly, fixes the effect probe last and
records admission/pre-observation durations. It keeps the same seeds, job and
attempt deadlines, CPU/memory/PID bounds and stopping rules. The initial run also
shared the host with the default dependency build and idle demonstration services;
those owned services were paused and the build had finished before the amended
run. The run-to-run change therefore cannot isolate a single causal improvement.
No failed run is replaced, excluded from the report or relabelled as success.

The executed results and limits are in [the Stage 3 report](../reports/stage3/REPORT.md).
For current independent review, use `reviews/stage3-review-packet.json`; archived
run packets bind their original byte-level manifests. Existing Windows worktrees
can restore checksum-bound assets with:

```bash
python scripts/normalize_evidence.py --fix --output .local/stage3/normalization-001.json
```

The tool changes only tracked evidence-format files whose LF-normalized bytes
exactly equal their committed Git blob. Files with real edits remain untouched.
It never recalculates or replaces recorded expected checksums.
