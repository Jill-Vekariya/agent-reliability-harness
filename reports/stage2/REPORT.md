# Stage 2 report — PARTIALLY VERIFIED

Historical checkpoint. See [resumed verification](RESUMED.md) for subsequent results.

1. **Outcome.** Authorization, one-use action approval, cancellation and conservative
   synthetic-provider budget controls are implemented in an isolated, unpublished
   patch. Local gates passed. Real PostgreSQL/Docker acceptance remains BLOCKED;
   this stage is not claimed complete or ready for public deployment.

2. **Scope and exact source.** Agent Reliability Harness only. Base revision:
   `bfd4d6f951a6e3d8e3d503cb96c6662ee0e258c6` (the verified local Stage 1 branch).
   Working branch: `feat/workflow-controls-stage2`; changes are uncommitted.
   Tested source SHA-256: `5590af78c4d6e1dc74e07ba34e8e4925d715a05f65ac5f034d1c244d5d049627`.
   The receipt includes dirty paths and individual source-file hashes. The earlier
   Stage 1 dirty worktree was left untouched. Public main was `0aa386e` when
   initially checked; Stage 2 has not been pushed, merged or run in CI.

3. **Evidence and actual checks.** Environment: `Linux-6.18.55-x86_64-with-glibc2.39`; Python 3.12.14,
   dependencies installed with `uv sync --locked --extra workflow` (exit 0).
   The exact gate command was:
   `uv run --no-sync python scripts/verify_workflow_controls.py --output .local/stage2/verification-003`.
   It returned **2**, deliberately reporting PARTIALLY VERIFIED because no dedicated
   PostgreSQL test database was configured. Within that run:

   | Check | Label | Actual result |
   |---|---|---|
   | Pytest | VERIFIED for executed tests | 181 passed, 33 explicitly skipped, 1 deprecation warning; exit 0 |
   | New control unit tests | VERIFIED | Fail-closed auth, role boundary, trace redaction, credential creation/upgrade preservation |
   | Ruff check and format | VERIFIED | Both exit 0 |
   | Mypy | VERIFIED | 42 source files; exit 0 |
   | Fixture data/task validation/review/split gates | VERIFIED | Each exit 0 |
   | Existing offline evaluation | VERIFIED | Exit 0; this is regression/safety evidence, not live model quality |
   | PostgreSQL tenant/race/recovery/budget/process tests | BLOCKED | All 33 DB-dependent cases skipped; no pass claim |
   | Schema upgrade in PostgreSQL WASM | PARTIALLY VERIFIED | PGlite 0.5.13 ran 001 then 002, converted a queued old effect job to waiting_approval and created a pending approval; exit 0. No native locking/concurrency proof |
   | Compose YAML | PARTIALLY VERIFIED | Parsed; loopback exposure and API-only credentials checked. No Docker build/start proof |
   | Stage 2 CI / hosted backend / real usage | UNVERIFIED | No publication or external usage |
   | Live provider / real spending | NOT APPLICABLE | Disabled; deterministic synthetic credits only |

   Full receipts, logs, JUnit and earlier runs are retained in the review package.
   Earlier runs are historical for their recorded dirty-source hashes. Baseline
   main CI runs 40527589602 and 40527576130 succeeded at `0aa386e`; they do not
   verify this patch.

4. **Changes and trade-offs.** Added `auth.py`, forward migration `002_controls.sql`,
   API tenant/role checks, allowlisted public traces, persistent approvals and
   operation/budget records. Claiming consumes an approval for one attempt; retries
   need a fresh approval. Job locking serializes cancellation, dispatch and finish.
   Reservations precede calls; unknown in-flight costs stay held. The fake provider
   uses the existing bounded credential-free child. No extra orchestration service
   or live provider dependency was introduced. Private raw evidence is retained.
   Demo credentials are not production identity; DB operators remain trusted.

5. **Failures, blockers and unverified claims.** Native PostgreSQL installation in
   the scratch environment failed (`apt-get update`, exit 100: setgroups/seteuid
   unavailable). The authorized device became unresponsive and then was reported
   Offline. A Stage 2 worktree was created there at the base revision before it
   disconnected; the patch has not been transferred back. Docker's daemon did
   respond once after startup, but no Stage 2 Docker execution was established.
   SQL transaction races, real-process restart tests and resource behavior remain
   unverified. The existing HTTP test client reports a deprecation warning; no
   dependency was upgraded to hide it. No failed evidence was deleted.

6. **Personal learning/contribution.** Explain approval binding and retry policy,
   the dispatch/crash window, lock ordering, conservative unknown costs and why
   accepted cancellation cannot prove an external request stopped. A bounded
   independent exercise is an operator-authorized uncertain-cost reconciliation
   command with immutable audit history, idempotent settlement and tenant tests.
   Independent implementation by the user has not been established; AI-assistance
   disclosures remain intact.

7. **Next scope and authorization.** First finish Stage 2: apply the prepared patch
   to a clean worktree based on `bfd4d6f`, run the native PostgreSQL/Docker suite,
   inspect every failed/skipped result, and retain the new receipt. Existing
   authorization covers local implementation and verification. Pushing, merging,
   public deployment and spending remain outside this performed scope. After
   Stage 2 acceptance and the user's `continue`, propose Stage 3's bounded
   failure-injection and evaluation protocol before executing experiments.
