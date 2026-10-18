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
