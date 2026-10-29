# Reproduce the private workflow deployment

This is a loopback-only local demonstration of durable, synthetic fixture jobs.
The original offline CLI, recorded evidence and read-only SQL sandbox remain in
place. Workflow state uses its own PostgreSQL database; the agent does not receive
its credentials. No live provider is constructed, and no model key is required.
Generated bearer identities demonstrate tenant authorization; they are not
production authentication.

## One complete setup path

Use the prepared Stage 5 worktree or apply the cumulative patch to the exact base
listed in the stage report. Public `main` does not yet contain these unpublished
workflow changes. Do not apply patches over an existing dirty worktree.

Prerequisites: Python 3.12, uv, Docker with Linux containers and Docker Compose v2.
From the project root:

```bash
uv sync --locked --extra workflow
uv run --no-sync python scripts/normalize_evidence.py --fix --output .local/stage5/checkout-bytes-001.json
uv run --no-sync arh data
uv run --no-sync python scripts/verify_workflow_deployment.py --project arh-local-001 --output .local/stage5/run-001
```

The same commands work in PowerShell. Durable worker execution occurs in Linux
containers. The verifier creates credentials only when missing, checks local
exposure/zero-spend settings, builds `Dockerfile.workflow` from the locked
dependencies and pinned Python base, initializes pinned PostgreSQL 16.15, checks
migration reentry, and runs all tests against a dedicated test database.
Database startup probes use TCP loopback. The pinned PostgreSQL entrypoint starts
a temporary Unix-socket server during first initialization; probing only that
socket can report readiness before the final server is available for restore.

The checkout repair restores LF bytes only when they exactly match the committed
Git blob. It preserves genuine edits and writes a separate receipt; it does not
regenerate evidence or replace trusted hashes. This is required for existing
Windows checkouts created before the LF attributes were applied. Use a fresh
receipt path on each run and inspect any files listed as genuinely changed.

The Dockerfile has separate `runtime` and `checks` targets. Only the checks target
installs Git, which the provenance tests need; the application target does not.
The verifier builds both and records their immutable image IDs against the same
source digest, including test sources, datasets, task definitions, regression
recordings and selected evidence. Continuation pins both IDs and refuses
missing checks-image receipts or changed source. Rebuild rather than editing an
old receipt to make it appear current. The source-context unit test creates its
own small synthetic Git checkout, so it does not require repository metadata to
be included in a deployment image.

It then runs four predefined jobs: a normal fixture, one approved synthetic
effect, one approved fake-provider call with known usage and one with unknown
usage. The synthetic budget is 100 credits; these are not currency. API and
database request limits remain in place. The verifier uses only loopback ports
8093 and 8094, then tears down its own source/restored containers and networks.
Persistent volumes and the backup are retained. It refuses a pre-existing
project before claiming ownership and does not tear down a refused project.

Use a new project name and new output directory for another complete run. Failed
checks are retained; the verifier never converts a skipped database test into a
pass. Its optional `--phase build|tests|demo|down` commands support explicit,
recorded continuation. Continuing a phase requires matching source hashes and
the image ID recorded by the build. Do not use a mutable image tag as a release
identity. Database and report volumes are never deleted by this procedure.

## Manual startup and configuration

```bash
uv run --no-sync python scripts/configure_workflow.py
uv run --no-sync python scripts/workflow_ops.py --project arh-local-manual validate
docker compose --env-file .env.workflow -f compose.workflow.yaml -p arh-local-manual build api
docker compose --env-file .env.workflow -f compose.workflow.yaml -p arh-local-manual up -d api worker-a worker-b
```

The generator refuses to replace existing credentials. `.env.workflow` and
`.local/workflow-auth.json` are ignored and excluded from Docker context. Do not
print, commit or include them in an evidence archive. Operators read the generated
auth file locally to select a tenant/approver token. The deployment validator
checks that both copies agree, rejects placeholders and duplicate config keys,
and refuses a non-loopback API port, an exposed database, a non-internal workflow
network, non-local execution or a nonzero live-provider budget.

Default manual API port: 8091. `ARH_WORKFLOW_API_PORT` selects another loopback
host port. `ARH_WORKFLOW_IMAGE` can select an image, but evidence must record its
immutable ID. CPU, memory, PID, read-only filesystem, dropped capability and
no-new-privileges settings are declared in `compose.workflow.yaml`. This small
stack is not a load-tested public service. Do not use `docker compose config`
without `--quiet` in a recorded terminal; full config contains local secrets.

## Health, logs, metrics and traces

- `/live` proves the API process can respond; it does not query PostgreSQL.
- `/ready` requires the complete expected migration/checksum map and a reachable
  database. Database unavailability or migration drift produces HTTP 503.
  The verifier allows a bounded 10-second readiness response because connection
  setup and query timeouts add to Docker networking overhead; the measured
  stopped-database response was 503 after 4.234 seconds, longer than the original
  four-second client deadline. Ordinary API requests retain a four-second client
  timeout. This does not claim a four-second readiness latency guarantee.
- `/metrics` requires a bearer credential and reports only that principal's
  tenant: job/attempt/operation states, queued-work age, stale-result rejections
  and configured synthetic-budget accounting. It uses fixed label sets and
  includes no tenant, subject, job, prompt, SQL or token labels. Unconfigured
  budget values are omitted rather than interpreted as free provider access.
- Structured API logs contain server-generated request/trace IDs and the job ID
  where applicable. OpenTelemetry HTTP and worker-attempt spans share persisted
  trace/parent IDs. Telemetry metadata is stored separately from the immutable
  payload hash, so repeated submissions still identify the same job.
- Span export is local JSON logging with an attribute allowlist. It has no
  network exporter and does not record raw exceptions, prompts, SQL, rows or
  provider payloads. This covers API-to-worker causality; the existing archival
  SQL-agent trace format remains separate. It does not claim GenAI convention
  compliance or an externally hosted trace backend.

Authenticated metrics queries perform database aggregation and are intended for
this bounded demonstration. A production deployment would need a reviewed
collection/authentication strategy and measured query cost. Worker health is
observed through claims, completion spans, attempt records and queue age; no
unverified worker liveness endpoint is advertised.

## Coordinated backup and fresh restore

Keep the selected immutable application image available locally. From the same
configured worktree, substitute its `sha256:...` image ID:

```bash
uv run --no-sync python scripts/workflow_ops.py --project arh-local-manual --image sha256:IMAGE_ID backup .local/backups/snapshot-001
uv run --no-sync python scripts/workflow_ops.py --project arh-local-restored restore .local/backups/snapshot-001
```

Backup validates the actually deployed image, stops API/worker writers, dumps
PostgreSQL with `pg_dump`, and snapshots the report/effect volume. SQLite files
use SQLite's backup API and integrity check, excluding their transient sidecars.
The manifest records image identity, migration checksums, PostgreSQL version and
file hashes. Credentials are excluded and must be retained/re-created separately.
Backups can contain job inputs/results and must remain private. POSIX outputs
use owner-only permissions; retain the workstation's user-only access controls.

Backup leaves writers stopped even on failure. Restore verifies checksums and
image/schema compatibility, refuses any existing target project containers or
volumes, and requires the same PostgreSQL major version. It uses a transactional
`pg_restore` and a bounded report archive restore into an empty report volume.
Archive paths, links and duplicates are rejected. The local-demo report limit is
32 MiB of file content and 4,096 files; archive input is bounded to 48 MiB.

Writers remain stopped after restore. Verify all six workflow-table fingerprints,
synthetic-effect records, tenant controls and reserved/spent credits before
starting the selected image. The provided verifier does that comparison and
checks replaying a restored idempotency key reuses the original job.
An interrupted/failed restore is retained for investigation; use another fresh
target rather than clearing it or overwriting existing state.

## Rollback and teardown

```bash
uv run --no-sync python scripts/workflow_ops.py --project arh-local-manual --image sha256:KNOWN_COMPATIBLE_IMAGE_ID rollback
docker compose --env-file .env.workflow -f compose.workflow.yaml -p arh-local-manual down --remove-orphans
```

Rollback compares the selected image's migration files with the running database
before stopping anything. It refuses incompatible images; it never performs a
down migration. The prior Stage 3 image knows only migrations 001/002 and cannot
serve the Stage 5 database after migration 003. For such an upgrade, retain a
pre-upgrade backup and restore it with its matching image into a fresh project.
Do not describe a restart with the same image as a cross-version code rollback.

Jobs bind source provenance as well as input payloads. Drain or preserve queued
work with its matching image before an upgrade; do not rewrite payload hashes to
make changed code accept old work. Existing Stage 1–3 volumes are outside this
demonstration's project names and must be left intact. Teardown deliberately
omits `-v`; volume deletion, publication and spending are separate decisions.

This work is AI-assisted. No production usage, public backend, independent user
implementation or live model result is claimed by the local deployment.

