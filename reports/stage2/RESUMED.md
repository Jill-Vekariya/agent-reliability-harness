# Stage 2 resumed verification — VERIFIED local engineering

The earlier REPORT.md is a historical checkpoint. Subsequent verification closed
the Docker and cleanup blockers. No public or production deployment is claimed.

- VERIFIED: isolated patch at base `bfd4d6f`; earlier dirty Stage 1 worktree untouched.
- VERIFIED: PostgreSQL 16.15 and 64 workflow checks (33 integration + 31 unit), exit 0.
- VERIFIED: normal Dockerfile build, normal-image startup/readiness, exit 0.
- VERIFIED: final full normal-image suite, **214 passed, zero failed/errors/skipped**.
  JUnit: `stage2-default-all-tests-004.xml`; log: `default-all-tests-004.log`.
- VERIFIED: final API probes: `/live` 200, `/ready` 200, anonymous `/jobs` 401,
  authenticated `/jobs` 200. A real composed q001 fixture job succeeded; duplicate
  submission returned the same persistent job identity.
- VERIFIED: network-disabled Docker CLI checks: all 37 tasks validated, and
  offline regression matched its expected 19/20 baseline with no regressions,
  incompatibilities, live model calls or spending; both commands exited 0.
- VERIFIED: task-owned stack stopped with `docker compose ... down`, exit 0.
  No task-owned containers remained; both `arh-stage2-resumed_workflow-db` and
  `arh-stage2-resumed_workflow-reports` were retained. No volume was deleted.

Failures remain preserved:

1. First full suite: 206 passed / 8 failed. Windows CRLF changed byte-bound evidence.
   The repair restored 207 files only when normalized bytes exactly matched their
   committed Git blobs. The two genuinely edited YAML files were left intact.
   `.gitattributes` now pins evidence formats to LF; expected checksums were unchanged.
2. Second suite: 213 passed / 1 failed. The workflow image lacked the writable
   offline-viewer artifact path. It now sets `ARH_ARTIFACT_DIR=/reports/artifacts`
   while retaining a read-only root filesystem.
3. Third suite: 213 passed / 1 failed. The final GET following an API restart hit
   the test client's one-second timeout. That read now uses the existing bounded
   reconnect observation helper. Its one-second per-request limit, 12-second total
   observation window and all state/attempt/accounting assertions remain intact;
   the first returned HTTP response is checked, including an explicit 200 assertion.
4. A supplemental native check recorded SQL parent-deadline failures. That receipt
   and failed run remain retained. The checker now pins its CLI root to the
   inspected checkout when reusing an environment; explicit-root native validation
   and regression passed, as did the same commands in the verified Docker image.
   SQL limits and expected outcomes were not changed.
5. Earlier offline rebuild and cached-image reference failures also remain recorded.

Final image ID:
`sha256:dca37f82d59e2ad0b0c98732895895c2f0263c31837d2d33955ca3d4d137e4e6`.
The receipt records source revision, dirty state, selected images, exact commands,
exit codes, JUnit counts, API observations and teardown. The sanitized closure
summary is included in the review package. The full raw archive remains at:
`C:/Users/jillv/Projects/ARH-Stage3-20261028/.local/stage3/remote-evidence-closure-001.zip`.
Its SHA-256 is
`e9c9b2aa92f3562f89b3984419125e15a123511c80451ca447d542c17355af40`.
Automatic approval review blocked its bulk export because it may contain private
logs/source. Nothing was deleted or hidden; use the retained on-device archive for
full log inspection.

This closes Stage 2's local engineering verification, not production authentication,
public usage or the remaining portfolio stages. No commit, push, merge, publication,
license choice or spending was performed.
