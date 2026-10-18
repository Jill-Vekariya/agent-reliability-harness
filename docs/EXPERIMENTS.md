# Study protocol — not yet measured

No live model calls have been made. USD 0 is authorized. The final corpus, grouped holdout, exact models/pricing, and human validation are pending; no headline freeze exists.

| Configuration | Model | Change | Expected tradeoff | Live outcome |
|---|---|---|---|---|
| A | Small, selection pending | Baseline | Simple agent, potentially more schema errors | Not yet measured |
| B | Same small model | Four optional interventions | Potential recovery with more tokens/steps | Not yet measured |
| C | Larger, selection pending | Same agent as B | Potential accuracy/cost tradeoff | Not yet measured |
| B minus schema retrieval | Same small model | On-demand tools only | Less context, potentially more schema guessing | Not yet measured |
| B minus pre-validation | Same small model | Mandatory sandbox retained | Less overhead, potentially less useful feedback | Not yet measured |
| B minus retry | Same small model | Stop on error | Lower cost, potentially fewer recoveries | Not yet measured |
| B minus clearer descriptions | Same small model | Valid concise descriptions | Fewer prompt tokens, potentially more misuse | Not yet measured |

Configurations under `experiments/` are executable-shape templates with intentionally unresolved model identifiers. They do not authorize calls. Freeze code/config/task/split/database/pricing hashes before test use. Safety controls never vary between arms. Four leave-one-out contrasts are conditional effects and can interact.

Target arithmetic: 60 test tasks × 7 configurations × 5 fresh attempts = 2,100 agent attempts, including 1,680 ordinary and 420 safety. API calls per attempt can exceed one. Actual current reviewed test tasks: zero. Dev/pilot/label-validation costs are additional.

Use five fresh independent attempts, never cached model outputs, for model reliability claims. Pass@5 assumes an oracle recognizes a successful candidate. Task-family bootstrap uses 10,000 resamples and paired families for contrasts; inspect small-family and degenerate intervals. Do not infer independent causal component effects from leave-one-out differences alone.

Operational failures retain their started attempt; infrastructure errors are separately visible. Never-started work is missing coverage. Interrupted attempts are retained and not silently replaced on resume. Insufficient five-attempt coverage leaves pass@5 undefined.

The demo recovery is a different prewritten script. It illustrates tool-error feedback but provides no empirical evidence that retries improve a model. A real failed or inconclusive intervention is an ownership/interview requirement once actual evidence exists.

## Before approving a pilot

Choose exact available model versions, official current prices and billing categories, verified context bounds, tasks/config hashes, max calls/tokens/retries, conservative pilot/full-study upper bounds, and a cumulative cap. Obtain explicit user approval once for that scope. Filling an example JSON file is not a record of conversational authorization.

## Coverage and estimands

Every campaign declares task/config/repetition attempt IDs before dispatch. Summary checkpoints record planned, reported, started-without-report, and never-started counts, plus unresolved ledger exposure. A started registry row is not proof a provider call occurred. Resume retains its identity and does not replace an interrupted sample. An incomplete resumed campaign exits nonzero through the CLI.

Ordinary task accuracy, safety behavior, unsafe decisions, and executed prohibited actions remain separate. Per-configuration metrics report observed correct/failed attempts, first sample successes over repetition-zero outcomes, tool-error attempts and observed recoveries, token totals, and measured cost/latency coverage. Recovery means a successful attempt containing an earlier tool error, not a causal estimate of retry benefit. Operational rates/latency intervals describe recorded outcomes; wholly missing tasks remain in planned coverage. Unknown usage leaves cost undefined and ledger exposure reserved. Incomplete coverage suppresses headline pass/cost values and paired effects; no stale Pareto file is retained.

Report configurations/models and dev/test partitions separately. Family bootstrap resamples entire clusters; paired contrasts require the same unique task/repetition identities and families. Five attempts per task are required for pass@5 and the headline repeated-sample summaries. Report task, family, and attempt counts, first-sample and recovery denominators, and unknown/missing observations. Call-level blocks divide blocked unsafe SQL proposals by detected unsafe proposals; zero proposals is undefined. Injection-conditional rates require observed injection exposure. The prohibited-SQL classifier remains a heuristic needing actual human labels.

## Freeze contract

For `--split test`, `experiments/freeze.json` must have schema version 1, `frozen: true`, actual `approved_by`/`approved_at`, matching `source_hash`, `dependency_lock_hash`, `task_hash`, `database_manifest_hash`, and `split_hash`; allowed `config_hashes` and full `approval_hashes`; and relative `review_packet_path`/`split_manifest_path` with their `_sha256` hashes. Approval hashes bind model, prices/context, task scope, caps, and campaign approval together. Files must remain inside the project. Source means all runtime Python files under `src`; Git revision/dirty state is also recorded in the run manifest.

The gate validates actual accepted review attestations and reviewer metadata, resolved disagreements, grouped/exposure checks, task/split agreement, an ordinary unexposed test set, gold lint, and exactly five repetitions. Re-freeze after a runtime/config/task/provenance change. Review/split tooling does not fabricate this manifest or authorize spending. The currently committed all-dev candidates cannot satisfy this gate. Freeze attestations are operator evidence, not independent identity verification or conversational permission.

For each planned leave-one-out contrast, use the row in the configuration table as its hypothesis, keep mandatory authorizer/process/budget controls fixed, compare against B on identical task distributions/repetitions, and record config/task/hash/seed and failure traces. Primary endpoint: paired ordinary pass@1 difference; cost/latency and safety are secondary outcomes. Use family intervals and report failed/inconclusive effects. Interactions prevent interpreting these conditional contrasts as independent component effects. No hypothesis is presently supported by live evidence.
