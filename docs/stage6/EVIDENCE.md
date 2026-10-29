# Evidence and exact source identity

Status: **Historical Stage 5 acceptance verified locally; human ownership work pending.**
Feature branch: `feat/durable-workflow-portfolio-20261029`. Its pull request tracks CI on the current head.
Captured 29 October 2026. This is not a new public release or a public backend deployment.

| Identity | Value |
| --- | --- |
| Local capture branch | `fix/stage5-resume-20261029` (pre-publication working tree) |
| Base commit | `bfd4d6f951a6e3d8e3d503cb96c6662ee0e258c6` |
| Selected runtime/test/data input digest | `6e51a5026bd5c467a9698ed15d3e65eabe6235bedfa385b3c2cf1d88b0279485` |
| Runtime image | `sha256:bc459f498d352ed6bfe37e9ee7212fbc5775e24d8b7b6b3195f44af1613bc94e` |
| Checks image | `sha256:b3f549286e549d7310ab0259a58922f85e92df08c9b56b65d8a98cfe94dc58d7` |
| Selected input hashes | 212, retained in [source context](evidence/source-context.json) |
| Executed project | `arh-stage5-tcp-20261029` |

At capture, the base commit existed only in the local worktree. Publication
also uploads its ancestor history. The [published source](https://github.com/Jill-Vekariya/agent-reliability-harness/tree/0aa386e847d383ba6bbff6ff0e20aab99b3dd791)
identifies the baseline before the workflow additions. Image labels and these
operator-collected hashes bind selected bytes; they are not a signed supply-chain attestation.

## Executed acceptance checks

| Check | Result and scope |
| --- | --- |
| Host setup | New Python 3.12.14 environment, uv 0.12.23, locked workflow install, dependency and pinned-data checks passed. |
| Build/config/migrations | Both Docker targets built, local exposure/zero-spend settings validated, migration and reentry passed. |
| Complete Docker suite | 235 passed; zero failures, errors or skips; one existing Starlette/httpx deprecation warning. [JUnit](evidence/full-tests.xml). |
| Bounded synthetic workload | Four admitted jobs succeeded; one logical effect and one sink invocation. No live provider calls. |
| Tenant/auth and observability | Unauthorized access rejected, other-tenant data hidden, metrics scoped; a representative persisted HTTP/worker trace linked. |
| Recovery and budgets | All six table fingerprints and effect records matched after fresh restore; spent 6 and reserved 10 of 100 synthetic credits retained. |
| Rollback | Existing-target restore and incompatible-image rollback refused; supported matching-image restart and restored idempotency verified. No cross-version downgrade claim. |
| Teardown | Both source and restore projects had no remaining containers; four named persistent volumes retained. |

[Commands](evidence/commands.json) include expected nonzero exits for refusal
checks. [Demonstration](evidence/demonstration.json), [health](evidence/health.json)
and [teardown](evidence/teardown.json) are safe synthetic summaries. Command
receipts replace local absolute workstation/interpreter prefixes with explicit
placeholders; private originals are retained. Backups, credentials and raw
private configuration are excluded.

## Stage 6 contribution validation

The [upstream documentation patch](UPSTREAM.md) was tested against pinned
PostgreSQL 18 in two local fixtures. Both showed Unix readiness during the
temporary initializer while TCP remained unavailable. The corrected check then
passed a real TCP SQL query and an initialized-volume restart; an intentional
initializer failure never produced healthy TCP status. Both containers were
removed and their two test volumes retained. [Version-18 receipt](evidence/upstream-postgres18.json).

[Ownership exercise](OWNERSHIP_EXERCISE.md), [interview route](INTERVIEW.md) and
[profile/pin proposals](PROFILE_PLAN.md) remain separate from completed personal
work. The independent exercise has not been implemented or reviewed.

## Public CI and historical evidence

Public main was observed at `0aa386e847d383ba6bbff6ff0e20aab99b3dd791`.
[Verify-and-release CI](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/40527576130)
and [the second recorded check](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/runs/40527589602)
were successful at that revision. They predate the workflow additions.
The feature branch must pass checks on its exact head before merge. Existing [v0.3.1 evidence](../../reports/releases/0.3.1/verification.json)
and [Stage 3 report](../../reports/stage3/REPORT.md) retain their original scopes/counts.

The public [saved-trace walkthrough](https://jill-vekariya.github.io/agent-reliability-harness/)
does not execute the local workflow. Current tests prove engineering behavior on
fixtures; no new human gold review, holdout, provider compatibility study or
measured model-quality improvement is claimed.
