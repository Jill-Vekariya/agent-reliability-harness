# Presenting this project honestly

Verified release: [v0.3.0](https://github.com/Jill-Vekariya/agent-reliability-harness/releases/tag/v0.3.0), with 145 tests passing in hosted CI and in the anonymously downloaded Docker image. [Current evidence](../reports/releases/0.3.0/verification.json) and the public demo support the factual project bullets below.

Use the public repository and browser walkthrough as project links. The browser walkthrough is static; Docker runs the SQL worker and offline regression. Read `OWNERSHIP.md` before using first-person authorship claims: the current implementation is AI-assisted, and personal review/exercises remain pending.

## Resume project entry

**Agent Reliability Harness | Python, SQLite, Docker, pytest, OpenTelemetry, GitHub Actions**

Current project description, suitable before completing personal ownership work:

> AI-assisted SQL-agent evaluation project with a protected SQLite worker, deterministic grading, trace replay, offline regression, spending controls, a Streamlit viewer, and automated container delivery. Includes synthetic failure and blocked-query demonstrations; live-model evaluation and human benchmark review are pending.

After you understand the implementation and complete the documented exercises, adapt these templates to your actual work:

* Implemented/reviewed **[components you actually implemented or reviewed]** in a SQL-agent evaluation harness; validated **[current executed test count]** engineering tests and a fixed 20-task synthetic regression suite in Docker with networking disabled.
* Investigated **[actual failure and commit]**, added **[your actual test or fix]**, and documented **[the supported result]** using reproducible traces and pinned runtime/data dependencies.

Keep the experimental bullet in `OWNERSHIP.md` pending until fresh model runs exist. Never describe the scripted recovery as an accuracy gain, 19/20 synthetic matches as model accuracy, or engineering tests as production scale.

## Make it readable by people and resume parsers

Use a one-column resume, conventional headings, selectable text, a readable project URL, and relevant terminology that is actually supported by the code. Match a role's requirements through completed work: Python/backend roles can assess subprocess supervision, SQLite, typed contracts, tests, and CI; AI engineering roles can assess agent evaluation, tool boundaries, reproducibility, and cost accounting. Include Docker, GitHub Actions, SQL, and pytest where relevant; explain each in an interview.

Do not add hidden text, invented employment, unsupported metrics, or instructions aimed at an automated reviewer. Selection depends on the role, resume, experience, competition, and interview; no project can guarantee passing every screening system.

## A 60-second introduction

“This project makes a SQL agent's behavior inspectable and reproducible. The agent has four tools, while each query runs through a read-only SQLite worker with an authorizer and execution limits. The evaluator grades typed result tables and rejects final answers without a complete current-attempt result. Saved responses support strict replay and current-tool regression with no model fallback. The project runs in Docker and has a public synthetic trace walkthrough. The engineering release is verified; I have not yet measured live model accuracy or completed human benchmark review. The implementation was AI-assisted; my completed contributions are recorded in the ownership log.”

Replace the final sentence only with your actual contributions. You should be able to explain every sentence and navigate to its implementation.

## Interview route through the repository

| Discussion | Code/evidence to open | Main tradeoff |
|---|---|---|
| Architecture | `agents/sql.py`, `tools/runtime.py`, `sandbox/runtime.py` | Small tool surface and extra process overhead |
| SQL boundary | `sandbox/worker.py`, `tests/integration/test_sandbox.py` | SQLite/process limits are scoped protections, not general sandbox security |
| Correctness | `evaluation/grading.py`, `tests/unit/test_grading.py` | Duplicate-aware matching and explicit numeric tolerance |
| Budget concurrency | `providers/budget.py`, `tests/unit/test_budget.py` | Conservative reservations can stop work early after uncertain usage |
| Reproducibility | `tracing/recording.py`, `tests/integration/test_regression.py` | Exact matching rejects stale recordings rather than silently continuing |
| Evaluation design | `docs/EXPERIMENTS.md`, `evaluation/statistics.py` | Fresh repeated samples, family splits, and honest missing evidence |
| Delivery | `Dockerfile`, `.github/workflows/ci.yml`, `compose.release.yaml` | Repeatable packaging; public walkthrough has no SQL backend |

## Personal completion checklist

1. Run the Docker demo and explain q001, q002, and s001 without reading a script.
2. Review the 15 specified tasks in `OWNERSHIP.md`; record your own SQL reasoning and any corrections.
3. Complete one grader exercise and one sandbox exercise, with your own commits and explanations.
4. Write one investigation from an actual trace and explain what evidence would change your diagnosis.
5. Practice the interview questions and answers in `INTERVIEW.md`.
6. Update this resume entry with your actual contributions and the current verification evidence.

These are user exercises, not automatically completed labels.

## Factual project bullets and demonstration

Use these as descriptions of the project. First-person contribution claims require your own completed work and understanding.

* SQL-agent reliability harness with isolated SQLite execution, typed duplicate-aware grading, strict trace replay, and current-tool regression.
* 145 automated engineering tests covering SQL authorization, process deadlines/cleanup, concurrent spending reservations, trace integrity, and incomplete campaign coverage; verified natively and in a network-disabled Docker container.
* Public synthetic trace walkthrough, versioned GitHub/GHCR delivery, pinned runtime/data/dependencies, and recorded CI/container evidence. Human-reviewed benchmarking and live-model comparisons remain pending.

Project: https://github.com/Jill-Vekariya/agent-reliability-harness

Demo: https://jill-vekariya.github.io/agent-reliability-harness/

| Time | Demonstrate and explain |
|---|---|
| 0-2 min | q001: attempt-local results and supported final answers |
| 2-5 min | q002 and the separate scripted recovery: visible failure, no empirical retry-gain claim |
| 5-8 min | s001 and the SQL worker: untrusted values, authorizer, read-only mode, process limits |
| 8-11 min | Budget/resume tests: atomic exposure accounting, unknown charges, preserved incompatibility |
| 11-13 min | Review/exposure manifests and missing-cohort test: no manufactured holdout or missing denominator |
| 13-15 min | Actual CI/release evidence and the next scoped live experiment |

Practice process supervision, SQLite transactions, typed contracts, and packaging for backend discussions; evaluation validity, provenance, leakage, and uncertainty for AI infrastructure discussions. Show code and actual evidence for each claim.
