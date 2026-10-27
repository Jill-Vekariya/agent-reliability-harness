# Agent Reliability Harness — interview practice

## Five-sentence technical summary

This project makes a SQL agent’s tool use and failures inspectable. It places database queries behind a bounded read-only worker and checks typed results. Saved traces support strict playback and regression against the current tools. The engineering goal is to distinguish correct answers, safe execution and reproducibility. The public demonstration uses synthetic saved responses, while real-model performance and human-reviewed benchmark results remain unmeasured.

This explains the project’s engineering purpose. Describe your own motivation and role using actual experience; this document does not invent either.

## Ten questions and simple answers

1. **What problem does it solve?** A plausible SQL answer may come from an invalid query or unsafe action. The harness records the steps and checks the result and execution boundaries separately.

2. **What are the four tools?** list_tables, describe_table, run_sql and final_answer. A small tool surface makes behavior easier to constrain and test.

3. **Why a separate worker?** The parent supervises execution and enforces a deadline while the worker restricts SQL. Process limits help contain expensive queries, within the documented host assumptions.

4. **Does read-only mean completely secure?** No. It blocks the tested write paths but does not protect against a compromised host, SDK or arbitrary malicious Python code.

5. **How are answers graded?** The grader compares typed result tables while preserving duplicate rows. A final answer must reference a complete result from that same attempt.

6. **Why not compare result rows greedily?** With numeric tolerance, one early match can consume the only valid partner for another row. Matching must account for the entire result.

7. **How does replay differ from regression?** Replay checks a compatible saved recording. Regression runs saved synthetic responses against current tools, so a tool behavior change can fail the gate.

8. **How are unknown provider charges handled?** The ledger keeps conservative reservations when usage is unknown. It does not automatically refund spending merely because response parsing failed.

9. **What does 29/30 mean?** It is the ordinary scripted-match result in the offline gate. It is not live model accuracy or a human-reviewed benchmark score.

10. **What work is yours personally?** Use the real ownership log. Explain which code, review or experiment you actually completed; prepared AI answers and tests do not prove your independent contribution.

## Study before an interview

- Trace one request through the tool runtime, worker and final-answer binding.
- Study duplicate-aware grading, NULL handling and numeric tolerance.
- Explain ledger reservation, known usage and unknown-charge recovery.
- Understand replay hashes, public-task exposure and genuine held-out data.
- Reproduce one failure and complete an ownership exercise independently.

See [current status](CURRENT_STATUS.md) and the existing project-specific interview and ownership material. These answers are practice aids, not completed personal contributions.
