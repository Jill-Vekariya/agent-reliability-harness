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
