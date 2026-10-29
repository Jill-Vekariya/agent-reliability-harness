# Interview route for the prepared deployment

Use project statements, then identify only personal work supported by the
[ownership log](../OWNERSHIP.md). The implementation and preparation are AI-assisted.

## A short project explanation

“The harness makes SQL-agent failures inspectable and reproducible. It combines
read-only supervised SQL execution, typed grading and strict trace replay with
a local durable workflow for leases, tenant-scoped access, one-use approvals
and budget reservations. The latest local deployment passed 235 engineering
tests and verified four synthetic jobs, telemetry, identical snapshot restore,
rollback refusal and cleanup. That establishes the tested engineering behavior;
human gold review, live-model quality and my independent exercise remain pending.”

This is a prepared explanation, not evidence that the owner can explain it.

| Question | Evidence to open and answer boundary |
| --- | --- |
| What is actually live? | Public saved-trace page versus executing local Docker services. No public SQL/model endpoint. |
| Why separate PostgreSQL from SQLite? | `workflow/store.py` and `sandbox/worker.py`: trusted durable state versus agent-accessible read-only query fixture. |
| Why is read-only SQLite insufficient? | Authorizer, bounded worker resources and parent I/O/deadline/cleanup; arbitrary Python and host death remain outside scope. |
| What stops a stale worker? | Claims/lease version and guarded completion in `store.py`; actual restart integration test. |
| Does a retry execute an effect twice? | Explain the adapter's logical effect key and uncertain operation state. Do not promise universal exactly-once behavior. |
| What does approval authorize? | Exact action hash/version/attempt; consumption and new approval on the tested retry path. No broad model-granted execution authority. |
| Why keep ten credits reserved after success? | Missing usage leaves an operation uncertain even when the job result succeeds. Six known credits were settled separately. |
| What connects admission to work? | Persisted request/trace/parent identifiers; representative HTTP and worker span assertion. Do not infer all production traces are complete. |
| Why did a four-second health request fail? | Correct 503 arrived in 4.234s in the same-image diagnosis; verifier readiness deadline became ten seconds. Distinguish a client deadline from a readiness SLA. |
| Why probe PostgreSQL through TCP? | Pinned image has a temporary Unix-only initialization server. Final-server readiness matters before restoring state. |
| What can rollback do? | Refuse schema-incompatible image before mutation; restart matching image. A true application downgrade needs separately tested compatible state/image. |
| What do 235 passing tests not prove? | Production security/scale, live-model accuracy, human review or individual authorship. Open exact source/image evidence and known limits. |

For a live code route use [the walkthrough](WALKTHROUGH.md), then explain the
[case study](CASE_STUDY.md) and [design alternatives](OVERVIEW.md).
The [earlier interview guide](../INTERVIEW.md) retains core grading, replay,
budget and evaluation questions with their historical verification scopes.
