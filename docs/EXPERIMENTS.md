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
