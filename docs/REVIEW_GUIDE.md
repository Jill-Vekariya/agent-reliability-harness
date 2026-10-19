# Review the engineering

This guide connects the project's claims to implementation and tests. Start with a saved failure, follow its boundary into code, and then inspect the assertion that protects it.

## A five-minute route

1. Open the [public walkthrough](https://jill-vekariya.github.io/agent-reliability-harness/). Compare q001's supported answer with q002's schema failure. Both are prewritten synthetic examples.
2. Read [`ToolRuntime.call`](../src/agent_reliability/tools/runtime.py). A final answer must reference a successful, complete result from the same attempt; the tool cannot invent a new result table.
3. Read [`Sandbox.run`](../src/agent_reliability/sandbox/runtime.py) and the worker's [`authorize`](../src/agent_reliability/sandbox/worker.py). Separate SQL policy from process supervision: read-only access does not bound query time or memory.
4. Inspect a [worker lifecycle failure test](../tests/integration/test_worker_lifecycle.py) and a [regression compatibility test](../tests/integration/test_regression.py). These provide concrete failure cases to discuss.
5. Check the [current CI](https://github.com/Jill-Vekariya/agent-reliability-harness/actions/workflows/ci.yml), [released-image evidence](../reports/releases/0.3.1/verification.json), and [remaining work](STATUS.md). An engineering test count is distinct from a model benchmark result.

## Code map

| Question | Implementation | Tests or evidence |
|---|---|---|
| How are agent requests and tool responses orchestrated? | [SQL agent](../src/agent_reliability/agents/sql.py), [typed models](../src/agent_reliability/models.py) | [Agent integration](../tests/integration/test_agent.py) |
| Can an answer invent, truncate or reuse a result? | [Tool runtime](../src/agent_reliability/tools/runtime.py), [grading](../src/agent_reliability/evaluation/grading.py) | [Final-answer integrity](../tests/unit/test_final_grade.py), [grader cases](../tests/unit/test_grading.py) |
| What happens if a worker hangs or floods output? | [Parent supervisor](../src/agent_reliability/sandbox/runtime.py), [SQL worker](../src/agent_reliability/sandbox/worker.py) | [Lifecycle faults](../tests/integration/test_worker_lifecycle.py), [SQL controls](../tests/integration/test_sandbox.py) |
| How are concurrent calls and uncertain charges handled? | [Budget ledger](../src/agent_reliability/providers/budget.py), [provider adapter](../src/agent_reliability/providers/openai_adapter.py) | [Budget cases](../tests/unit/test_budget.py), [transport failures](../tests/unit/test_provider_hardening.py) |
| What makes a recording compatible with today's tools? | [Trace validation](../src/agent_reliability/tracing/recording.py), [runner](../src/agent_reliability/runner.py) | [Recording integrity](../tests/integration/test_recording.py), [resume/regression](../tests/integration/test_regression.py) |
| Can missing attempts make a result look better? | [Campaign runner](../src/agent_reliability/live.py), [statistics](../src/agent_reliability/evaluation/statistics.py) | [Campaign coverage](../tests/unit/test_campaign_metrics.py), [interrupted runs](../tests/integration/test_live_campaign.py) |
| How is benchmark exposure tracked? | [Review and split checks](../src/agent_reliability/evaluation/review.py), [development manifest](../tasks/development_exposure.json) | [Review integration](../tests/integration/test_review.py), [dataset card](DATASET_CARD.md) |
| What actually runs in the public demo? | [Static exporter](../src/agent_reliability/reporting/public_demo.py), [browser code](../web/app.js) | [Export boundary and encoding tests](../tests/integration/test_public_demo.py) |

## Three decisions to challenge

**Fresh subprocess versus in-process SQL.** A separate worker permits a parent deadline and cleanup when query execution stalls. Process startup adds overhead. The SQL boundary does not confine arbitrary malicious Python, compromised dependencies or the host. See the [threat model](THREAT_MODEL.md).

**Exact replay versus current-tool regression.** Replay shows a saved trace. Regression reuses recorded provider responses while running current tools, and rejects a response if its model-visible request no longer matches. Compatibility is deliberately strict; changing a tool may require an explicitly reviewed new recording. See the [reproduction guide](REPRODUCIBILITY.md).

**Conservative reservations versus utilization.** The ledger reserves an upper cost bound transactionally. Unknown usage retains exposure and stops further requests instead of silently refunding possibly spent funds. This can underuse a budget; tighter accounting needs real-provider validation. See the [design decisions](DECISIONS.md) and [experiment protocol](EXPERIMENTS.md).

## Reproduce a claim

After the [README setup](../README.md#quick-start), on Linux/macOS:

```bash
# Focused execution-boundary and recording checks.
uv run --no-sync pytest tests/integration/test_worker_lifecycle.py tests/integration/test_regression.py

# Full engineering gate and all synthetic current-tool cases.
make ci
uv run --no-sync arh eval --all
```

On Windows use Linux Docker and `TEST_PROJECT.cmd`. Keep the expected q002 schema failure visible. The public 37-task development set is not a clean holdout, and no fresh provider study has been performed.

## Contribution and interview context

The implementation is AI-assisted. [OWNERSHIP.md](OWNERSHIP.md) records completed work and pending personal exercises; [INTERVIEW.md](INTERVIEW.md) provides implementation-linked questions. A useful discussion is to reproduce one failure, predict what breaks without its fix, explain the test, and identify the remaining limitation. Personal authorship and review claims should refer to actual completed contributions.
