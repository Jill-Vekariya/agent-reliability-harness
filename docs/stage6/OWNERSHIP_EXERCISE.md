# Independent ownership exercise: read-only budget audit

**Status: assigned/prepared, not implemented or reviewed.** The existing ownership
record and earlier pending exercises remain unchanged. Estimated scope: two to
four focused hours, then a review of the real diff and explanation. No billing,
public hosting, external messages or migration is required.

## Feature to implement yourself

Add an authenticated `GET /budget/audit` endpoint backed by a read-only store
query. Report the caller tenant's recorded reserved/spent synthetic credits,
the totals implied by its operation ledger, and explicit consistency flags.
Use the current Principal; do not accept a caller-supplied tenant override.

Expected reserved exposure includes `reserved`, `in_flight` and `uncertain`
operations. Expected spend comes from settled successful operations. Inspect the
current store/model implementation rather than copying these words into SQL
without checking state and null semantics. Missing budget configuration must be
explicitly distinguishable from a configured zero limit.

Use a single statement/snapshot for the comparison so concurrent reservation or
settlement cannot create an artificial discrepancy between separate reads. This
endpoint must never release, settle, refund or mutate an operation. Do not add a
new provider path, expose database credentials, or claim currency billing.

## Acceptance criteria

1. Add a typed response and store operation using a consistent read snapshot;
   explain isolation and the treatment of missing/unknown usage.
2. Unauthenticated requests are rejected. Tenant B cannot see Tenant A's audit,
   including when it supplies misleading headers or extra query parameters.
3. Test empty/unconfigured, ordinary settled, held uncertain and deliberately
   inconsistent recorded-budget fixtures. Both recorded and computed totals
   remain visible; a mismatch must not be hidden by recalculating stored values.
4. A real PostgreSQL concurrency test exercises reservation/settlement while
   auditing and explains why consistent snapshots do not imply a permanent balance.
5. Demonstrate no database writes and unchanged job/operation/budget rows after
   the audit. Avoid returning prompts, SQL, tokens, job payloads or other tenants.
6. Run the focused checks and the full Docker path from the modified source.
   Keep failures, exact revision and output counts. Do not reuse this branch's
   235-test result as evidence for new code.
7. Explain one alternative, one concurrency failure a naive implementation would
   have, and why uncertain exposure cannot automatically be refunded.

Suggested scope: `workflow/store.py`, `workflow/api.py`, a typed response where
appropriate, focused unit/integration tests and a short endpoint description.
Keep unrelated refactoring and schema changes out of the exercise.

## Review record — leave pending until real work exists

| Field | Current state |
| --- | --- |
| Owner implementation commit/diff | PENDING |
| Owner's explanation and trade-off | PENDING |
| Executed checks on that code | PENDING |
| Reviewer findings and corrections | PENDING |
| Accepted personal contribution | PENDING |

Bring the actual diff, command receipts and your explanation for review. Automated
tests or this prepared solution brief do not establish independent understanding.
Retain AI assistance disclosures and distinguish later assisted work from work
you completed independently. See [OWNERSHIP.md](../OWNERSHIP.md).
