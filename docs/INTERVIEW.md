# Questions tied to this implementation

1. Why is a multiset different from a set? Show how duplicate counts matter to an aggregate/join bug.
2. Why can greedy numeric-tolerance matching fail? Walk through the overlapping-match unit test and its augmenting path.
3. Why keep SQL-answer accuracy, behavior success, unsafe proposals, and successful enforcement separate?
4. Why does SQLite's lock timeout not stop an expensive join? Explain progress checks plus the parent process deadline.
5. What does the authorizer see for COUNT(*)? Explain the real implementation bug that the tests found.
6. Why does a stored tool result need an attempt-local ID? Explain the forged Boolean/integer final-answer test.
7. What is the difference between exact replay and regression? Why must changed tool output invalidate a later model response?
8. Why does the fixture suite's scripted result-match count say nothing about a live model's accuracy?
9. Why group related question families in one split? What changes when a test set has already been inspected?
10. Why bootstrap families rather than individual repeated attempts? Explain paired task comparisons without claiming matched model randomness.
11. What oracle does pass@5 assume? Why isn't it the performance of an unimplemented retry selector?
12. What denominator makes a conditional block rate undefined? Explain why zero unsafe proposals cannot yield a 100% observed block rate.
13. How do reservations prevent concurrent overspending? What happens after a provider timeout with missing usage?
14. Why is the full context-window reservation conservative? What would need testing before tightening it?
15. What did one real failed or inconclusive intervention teach you? Currently pending; do not substitute the scripted recovery for measured evidence.

Answers should cite actual code/tests/artifacts rather than memorized performance claims. See milestone exercises for additional questions.

## Answer notes to practice, not memorize

1. A set removes duplicate rows. A multiset retains counts, so an extra join row fails even if all distinct values match. `evaluation/grading.py` also checks row width and types.
2. One approximate row can match two expected rows while another can match only the first. Greedily taking the first candidate may reject a valid assignment. The matcher searches an augmenting path to reassign the earlier match.
3. Correct results and safe behavior answer different questions. An injected script can propose DELETE, be blocked, and then refuse: enforcement worked while the decision was unsafe. Keep the denominators explicit.
4. SQLite's connection timeout concerns database locks. The progress handler limits VM work; worker resource limits constrain allocation/CPU; the parent separately terminates, kills if necessary, and reaps a stalled process.
5. SQLite can call the authorizer with an empty column and no database name for COUNT(*). The implementation permits that narrowly scoped read on an approved table. It does not permit arbitrary schema access.
6. A reference belongs to one attempt's result registry. Final rows are compared through canonical typed JSON, so a forged `true` cannot pass as integer `1` merely because Python considers them equal.
7. Replay validates and displays a saved trace. Regression reuses saved provider responses but executes today's tools/grader. If tool output changes the next model request, a recorded response no longer belongs to that request and the attempt fails as incompatible.
8. Fixture responses were written in advance. A match shows that code handled a predefined path; it says nothing about how often a live model chooses that path.
9. Related templates can leak a solution across dev/test. Assign families as groups before tuning. An inspected test set is no longer a clean holdout and needs honest disclosure or replacement before a headline claim.
10. Attempts within one question family are dependent. Family bootstrap resamples those clusters; paired configuration comparisons preserve the task/family association. Matching task IDs does not make stochastic model samples share random draws.
11. Pass@5 assumes an oracle recognizes at least one correct answer among five attempts. Without an implemented, independently evaluated selector, it is not deployed retry-system accuracy.
12. Blocks divided by unsafe proposals is undefined when proposals are zero. Report no observed proposals and the denominator; do not claim a measured 100% block rate.
13. The ledger reserves an upper bound inside a SQLite transaction before a request. Concurrent requests share exposure accounting. Unknown usage after timeout leaves a reservation unresolved instead of freeing potentially spent funds.
14. A full supported context plus output bound can be much larger than actual usage. It is conservative. Tighter token counting would require model-specific compatibility tests, billable-category coverage, and a documented margin before spending.
15. No real model intervention has been measured yet. Three actual implementation bugs are documented in `DECISIONS.md`; they are engineering lessons, not live-model treatment results. Explain one of those honestly, then describe the planned experiment.

## Design follow-ups

* **Why no Kubernetes or vector database?** One local registry, one public SQL fixture, and isolated subprocesses meet the current workload. More infrastructure would add operational work without evidence of a bottleneck.
* **What would change for production?** Start with an actual workload and trust model: tenant separation, authentication/rate limits for any public backend, secrets management, operational monitoring, data governance, and measured reliability targets. The current static public demo intentionally has no SQL/model endpoint.
* **What is the largest open risk?** The corpus and classifier lack human validation, and provider compatibility has only fake-transport tests. Engineering tests cannot replace that evidence.
* **What did you personally build?** State the AI assistance, open the actual ownership log, and identify your own completed commits/reviews. Pending exercises are not contributions.

For a resume entry and short spoken introduction, see `PORTFOLIO.md`.

## Audit cases to explain from code

| Question | Answer outline and evidence to open |
|---|---|
| Why does this project exist, and what has it proved? | Inspectable SQL-agent failures, protected execution, typed grading, and reproducible recordings. `README.md`, `docs/STATUS.md`. Engineering paths are tested; live-model benefit remains unmeasured. |
| Why is an authorizer useful if SQLite is already read-only? | Read-only protects file writes; authorizer policy also restricts tables, schema access, functions, PRAGMA, and attachments. `sandbox/worker.py`, SQL rejection tests. Neither confines arbitrary Python. |
| Can the parent deadline miss a hang? | The old blocking stdin write preceded the timer. The selector loop now includes input/output/waiting, then cleanup. Open `sandbox/runtime.py` and the blocked-input, output-flood, SIGTERM-resistant, and parent-interruption tests. Host death/process creation remain outside the guarantee. |
| Why round authorization and exposure differently? | A USD 0.0000009 cap cannot authorize a USD 0.000001 reservation. Floor caps and ceil charges in integer microdollars; exact fractions avoid Decimal-context boundary rounding. Open `providers/budget.py`, `priced_usd`, budget/atomic-json tests. |
| What if the provider bills but decoding fails? | Known usage settles before tool-response decoding. Missing/malformed usage, timeout, or operator interrupt after dispatch retains exposure and freezes new requests. `test_provider_hardening.py` uses fake transports only. |
| Can a failed regression turn green on resume? | Previously the cached branch skipped compatibility checks. Both paths now compare recorded model payloads/errors; identity and manifest changes reject resume. Open the resumed-incompatibility and changed-cached-replay tests. |
| Does a checksum establish authenticity? | A self-hash can be recomputed by an editor. Strict replay requires a trusted baseline/git hash and hashes/parses the same bounded bytes. Open `tracing/recording.py` and rehashed-payload tests. |
| Why not simply split these 37 tasks into test/dev? | They are already public dev cases. `development_exposure.json` protects their connected groups; the draft test count is zero. New unexposed families and actual review are required. Near-duplicate heuristics are not semantic proof. |
| Does a valid review packet prove human review? | It proves internally consistent attestations against current content, not identity or diligence. Reviewers/date/assessments/disagreements remain real human work. No automated promotion occurs. `evaluation/review.py`. |
| Why retain an entirely unobserved task cohort? | Inferring denominators only from completed rows hides operational gaps. Planned identities/checkpoints distinguish reported, started-without-report, and never-started work; incomplete coverage suppresses headline results. Missing-cohort/live-interruption tests. |
| What does first sample or recovery mean here? | First sample is repetition zero across tasks, distinct from all five repeated outcomes. Recovery is an observed successful attempt after a tool error, not a causal retry effect. Cite explicit numerator/denominator fields in `evaluation/statistics.py`. |
| Why use family bootstrap and paired comparisons? | Related templates/repetitions are correlated. Resample whole families and preserve matching task/repetition coverage across configs. Few-family/degenerate intervals need disclosure; pass@5 still assumes an oracle. |
| What would you change with more time? | Prioritize genuine gold review and unexposed families, then a scoped/priced live compatibility pilot, fresh paired study and actual failure labels. Avoid adding distributed infrastructure without a workload. |

Practice by reproducing one case, drawing its trust boundary, predicting the failed assertion without the fix, and then showing the recorded test result. Do not claim these AI-assisted fixes as personal authorship or empirical model improvements.
