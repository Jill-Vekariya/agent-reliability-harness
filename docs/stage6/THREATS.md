# Deployment threat model and remaining limits

This supplements [the core SQL threat model](../THREAT_MODEL.md). It describes a
bounded local demonstration and the current verification, not production certification.

| Boundary | Enforcement and evidence | Remaining limit |
| --- | --- | --- |
| Caller to API | Generated bearer-to-principal mapping; tenant-scoped store access; unauthorized/cross-tenant checks | Demonstration auth, not production identity, rotation, account recovery or public rate limiting |
| Approval to execution | Persisted one-use decision bound to action hash/version/attempt; worker checks state | Test driver approves predefined synthetic actions; no human approval quality measurement |
| Worker to SQL | Trusted supervisor and read-only authorized SQLite child with resource/output/deadline controls | No arbitrary Python upload boundary; host/kernel compromise is outside scope; Windows uses Linux containers |
| Agent versus workflow state | PostgreSQL credentials only in trusted service environment; SQLite remains separate | Compromised trusted service/host can access workflow state |
| Lease ownership | PostgreSQL claims, heartbeats and fenced completion; real restart tests | External effects still need adapter deduplication/reconciliation; general exactly-once is not claimed |
| Synthetic budget | Reservation before dispatch; known usage settles; unknown exposure stays held | Credits are not real provider billing; no new priced live-provider compatibility evidence |
| Public browser walkthrough | Static saved synthetic traces; no public SQL/model API | Browser content and exported files are illustrations/evidence views, not a controller security boundary |
| Telemetry | Tenant-authenticated fixed-label metrics and allowlisted local JSON spans | No external trace backend, measured production metric cost, or GenAI convention compliance claim |
| Snapshot recovery | Coordinated writer stop, checksums, matching schema/image, fresh-target restore and archive limits | Backup is private data; external copy/recovery and cross-version application downgrade are unverified |
| Source evidence | Selected file hashes, immutable local images and recorded expected exits | Operator-collected, unsigned; a hostile maintainer can replace trusted references |

The complete run uses an internal database network, loopback-only API binding,
non-root/read-only application containers, dropped capabilities, zero live-call
budget and CPU/memory/PID limits. The API's DB-dependent readiness has a bounded
verifier deadline; liveness does not require the DB. No production latency or
availability target has been measured.

Before a public executing backend: review real identity/authorization, secrets,
tenant load and retention, abuse controls, provider access/pricing and stopping
rules, monitoring, deployment recovery and operating ownership. This branch does
not authorize that deployment. Existing empirical limits remain: 37 exposed dev
tasks, zero independent gold reviews, no valid unseen test set and no measured
live-model benefit.
