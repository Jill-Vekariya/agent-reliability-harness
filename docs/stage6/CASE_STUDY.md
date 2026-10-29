# Failure recovery: keep the failed evidence

The local continuation retained each failed attempt, changed the demonstrated
boundary, and ran a new verification. These are engineering findings from an
AI-assisted implementation, not personal authorship or live-model results.

## Byte-bound evidence broke after a Windows checkout

The first new complete suite had 225 passes and eight failures. The public export,
regression and review checks rejected evidence/database-manifest hashes. Comparing
raw bytes, LF-normalized bytes and `git show HEAD:path` showed CRLF-only changes.
For example, the dataset manifest's trusted LF SHA-256 remained
`f0437b180814bf7537e3188fdea89c741a4e0c010a361a094869ca86eff24860`.

The existing guarded normalization tool restored 207 files only where normalized
bytes exactly matched their committed blobs; it reported no genuinely edited
files to leave aside. Expected hashes and old receipts were not regenerated.
The image-source record was expanded to include copied datasets, tasks,
regression recordings and evidence. Images were rebuilt before further checks.

## A client deadline obscured correct health behavior

Four synthetic jobs, tenant checks, metrics and trace correlation passed, then
the verifier timed out after four seconds during the stopped-database `/ready`
request. A separate same-image probe observed `/live` returning 200 in 0.125s and
`/ready` returning the expected 503 in 4.234s. Only the verifier's readiness
response deadline changed to a bounded ten seconds; ordinary calls retain four
seconds. The required HTTP status was not weakened or polled away. This does not
establish a readiness latency SLA.

## Fresh restore reached an initialization window

The next complete run passed 235 tests and the bounded workload, health and
coordinated backup. Restore then failed while reading the fresh database server's
version. The startup probe used the default Unix socket. Inspection of the exact
pinned PostgreSQL 16.15 entrypoint showed a temporary Unix-only server during
initialization. A probe accepting that temporary server is the supported diagnosis
of the race; the original subprocess's classified error alone did not prove it.

Compose health and the explicit startup wait now probe TCP loopback. A fresh run
then completed restore, identical fingerprints for all six workflow tables and
the synthetic-effect sink, expected refusal of an existing target, incompatible
rollback refusal, matching-image restart and teardown. The failed restore and
its retained volume remain separate; they were not overwritten.

## What process recovery actually proves

The real PostgreSQL restart test starts API/worker subprocesses, persists an
approval, kills a worker after a synthetic provider operation is dispatched,
expires its lease for controlled fault injection, then starts another worker.
The operation remains uncertain and its ten-unit reservation remains held. A new
approval permits another attempt; the final API reads the persisted successful
job, lost/succeeded attempts, uncertain/succeeded operations and six spent units.

This proves the tested state transitions under the stated fixture and fault
model. It does not make remote provider effects universally exactly once, settle
unknown charges, measure human approval quality, or establish production uptime.
The original restart timeout is retained; it was not reproduced in the passing
focused and complete Docker runs, and no unsupported single-cause explanation
is assigned to that earlier timeout.

## Retained run ledger

| Attempt | Actual outcome |
| --- | --- |
| Original Stage 5 container check | 226 passed, three failed; wrapper exit 124 |
| First resumed build | Failed fetching pinned hatchling from PyPI; a fresh retry built both targets |
| Focused resumed checks | All three previously failing checks passed |
| First resumed full suite | 225 passed, eight byte-provenance failures; no skips |
| Byte-repaired suite | 235 passed; next demo hit the four-second client deadline |
| Readiness-amended full run | 235 passed; fresh restore hit the startup window |
| TCP-startup full run | 235 passed; all 21 recorded commands met their expected exits; full acceptance passed |

Use [exact current receipts](EVIDENCE.md). Earlier evidence remains in the private
worktree's `.local/stage5` directories and the continuation review; no prior
failure is relabelled as success.
