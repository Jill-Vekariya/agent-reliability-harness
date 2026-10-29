# Reproduce and present the local workflow

Use the prepared branch described in [the evidence index](EVIDENCE.md). Public
main has not received these additions. Docker must use Linux containers; the
native Windows SQL worker is intentionally unsupported.

## Complete setup and test path

From the worktree root, with Git, Python 3.12, uv and Docker Compose available:

```bash
uv sync --locked --extra workflow
uv run --no-sync python scripts/normalize_evidence.py --fix --output .local/stage5/checkout-002.json
uv run --no-sync arh data
uv run --no-sync python scripts/verify_workflow_deployment.py --project arh-walkthrough-001 --port 8095 --phase all --output .local/stage5/walkthrough-001
```

The fresh locked host install and the complete Docker path were executed on
29 October 2026. The repair restores only exact committed blobs; inspect its
receipt rather than rewriting expected hashes. New project/output names are
mandatory because volumes, schemas and prior failed evidence are retained.

The all-phase command builds runtime/checks images, validates local exposure and
zero spend, starts PostgreSQL, applies migrations twice, runs the complete suite,
executes four jobs, checks auth/tenant isolation and telemetry, interrupts the
task database, backs up, restores to a fresh project and tests rollback/refusals.
Its finally block tears down owned containers and networks without deleting volumes.

For a recorded phase continuation, use the same project and matching build
metadata, with a new output path on each command:

```bash
uv run --no-sync python scripts/verify_workflow_deployment.py --project arh-review-001 --port 8095 --phase build --output .local/stage5/review-build-001
uv run --no-sync python scripts/verify_workflow_deployment.py --project arh-review-001 --port 8095 --phase tests --output .local/stage5/review-tests-001
uv run --no-sync python scripts/verify_workflow_deployment.py --project arh-review-001 --port 8095 --phase demo --output .local/stage5/review-demo-001
```

The final demo phase performs teardown. If stopping after tests, use the verifier's
`--phase down` with the same project and another fresh output directory. Source or
image mismatch requires a new build; do not edit receipts to claim a match.
Manual interactive startup, token selection, backup and rollback commands are
in [LOCAL_DEPLOYMENT.md](../LOCAL_DEPLOYMENT.md).

## Walkthrough script

| Time | Show and explain |
| --- | --- |
| 0–1 min | Define the two experiences: public saved-trace page and executing local Docker application. State that all provider/effect inputs here are synthetic. |
| 1–3 min | Open the architecture and `workflow/api.py`, `store.py`, `worker.py`. Explain tenant scope, idempotency, one-use approval and lease fencing. |
| 3–5 min | Show the real restart integration test. It kills an actual worker after dispatch, retains uncertain exposure, requires a fresh approval, and observes persisted results after API restart. |
| 5–7 min | Open the retained complete-run receipts: 235 tests, four jobs, known spend 6 and unknown reservation 10 of 100 synthetic units. Show representative HTTP/worker trace linkage. |
| 7–9 min | Show liveness 200/readiness 503 during the DB outage, matching restored fingerprints, rollback refusal and two empty container lists after teardown. |
| 9–10 min | State the limits and actual ownership status. Present the independent exercise without claiming it is completed. |

Run the automated verification before presenting or allow extra time for downloads
and Docker builds. Do not promise that a clean build fits a ten-minute talk.
Useful safe receipts are `commands.json`, `full-tests.xml`, `demonstration.json`,
`health-observations.json` and `teardown.json` in the selected output directory.
Do not display `.env.workflow`, the private auth mapping or raw backup contents.

## Failure to demonstrate from retained evidence

The successful process-restart test is
`tests/integration/test_workflow_postgres.py::test_real_api_and_worker_process_restarts_preserve_approvals_and_uncertain_cost`.
It uses real PostgreSQL and subprocesses with a fake provider. The initial failed
deployment attempts remain separate from the passing run; see [the case study](CASE_STUDY.md).
