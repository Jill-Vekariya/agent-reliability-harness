# Presenting this project honestly

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
