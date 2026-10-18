"""Fresh campaign execution. No invocation is authorized by the bundled templates."""

import json
import os
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from .agents import SQLAgent
from .evaluation.grading import grade, prohibited_sql
from .evaluation.review import check_grouped_split, check_reviews
from .evaluation.tasks import database_for_task, lint_tasks, load_tasks, task_hash
from .models import Limits
from .providers.budget import BudgetExceeded, Ledger
from .providers.openai_adapter import OpenAIProvider, read_approval, validate_approval
from .runner import environment_manifest
from .sandbox import Sandbox
from .tracing.recording import load_trace, save_trace
from .util import digest, file_hash, write_json


def validate_headline_freeze(
    root: Path, config: dict[str, Any], repetitions: int, *, approval: dict[str, Any] | None = None
) -> None:
    """Validate attestations/provenance; a file is never conversational authorization."""
    tasks = load_tasks(root)
    freeze_path = root / "experiments/freeze.json"
    if (
        repetitions != 5
        or not freeze_path.is_file()
        or any(task.review_status != "human_reviewed" for task in tasks)
    ):
        raise BudgetExceeded(
            "Headline test campaign requires reviewed corpus, freeze manifest, and five fresh attempts"
        )
    freeze = json.loads(freeze_path.read_text())
    if (
        type(freeze.get("schema_version")) is not int
        or freeze["schema_version"] != 1
        or freeze.get("frozen") is not True
        or not freeze.get("approved_by")
        or not freeze.get("approved_at")
    ):
        raise BudgetExceeded("Incomplete freeze attestation")
    current = environment_manifest(root, config)
    for key in (
        "source_hash",
        "dependency_lock_hash",
        "task_hash",
        "database_manifest_hash",
        "split_hash",
    ):
        if freeze.get(key) != current[key]:
            raise BudgetExceeded("Frozen provenance changed: " + key)
    if digest(config) not in freeze.get("config_hashes", []):
        raise BudgetExceeded("Configuration is outside frozen scope")
    if approval is None or digest(approval) not in freeze.get("approval_hashes", []):
        raise BudgetExceeded("Approval/pricing is outside frozen scope")

    def artifact(name: str) -> dict[str, Any]:
        relative = freeze.get(name + "_path")
        if not isinstance(relative, str):
            raise BudgetExceeded("Frozen " + name + " path is required")
        path = root / relative
        if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
            raise BudgetExceeded("Frozen artifact escapes project root")
        if not path.is_file() or file_hash(path) != freeze.get(name + "_sha256"):
            raise BudgetExceeded("Frozen artifact changed: " + name)
        return json.loads(path.read_text())

    packet, split_plan = artifact("review_packet"), artifact("split_manifest")
    review = check_reviews(root, packet)
    if not review["ready_for_metadata_review"]:
        raise BudgetExceeded("Human review attestations are incomplete or disputed")
    if any(
        not any(
            record.get("task_id") == task.id
            and record.get("status") == "accept"
            and record.get("reviewer_id") == task.reviewer
            for record in packet["reviews"]
        )
        for task in tasks
    ):
        raise BudgetExceeded("Task reviewer metadata does not match accepted attestations")
    if check_grouped_split(root, split_plan) or any(
        split_plan["assignments"].get(task.id) != task.split for task in tasks
    ):
        raise BudgetExceeded("Frozen grouped split is invalid or differs from task metadata")
    if not any(task.split == "test" and task.category == "ordinary" for task in tasks):
        raise BudgetExceeded("No unexposed ordinary held-out tasks are available")
    if lint_tasks(root):
        raise BudgetExceeded("Frozen task validation failed")


def run_live(
    root: Path,
    config: dict[str, Any],
    approval_path: Path,
    split: str,
    repetitions: int,
    resume: Path | None = None,
) -> dict[str, Any]:
    approval = read_approval(approval_path)
    validate_approval(approval, config, task_hash(root))
    if Decimal(os.environ.get("API_BUDGET_USD", "0")) <= 0:
        raise BudgetExceeded("API_BUDGET_USD=0; no provider request was made")
    if repetitions < 1 or repetitions > 5:
        raise ValueError("Repetitions must be 1..5; headline campaigns require exactly five")
    tasks = [
        t for t in load_tasks(root) if t.split == split and t.id in approval.get("task_ids", [])
    ]
    if not tasks or set(t.id for t in tasks) != set(approval.get("task_ids", [])):
        raise BudgetExceeded("Approved task scope does not match selected split")
    if len(tasks) * repetitions > int(approval.get("max_attempts", 0)):
        raise BudgetExceeded("Approved attempt count would be exceeded")
    if split == "test":
        validate_headline_freeze(root, config, repetitions, approval=approval)
    limits = Limits.model_validate(config.get("limits", {}))
    campaign_id = str(approval["campaign_id"])
    if not campaign_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Campaign ID must contain only letters, numbers, hyphens, underscores")
    artifact_base = Path(os.environ.get("ARH_ARTIFACT_DIR", str(root / "artifacts")))
    run_dir = resume or artifact_base / "live" / campaign_id
    manifest = environment_manifest(root, config)
    manifest.update(
        {
            "mode": "record",
            "origin": "live",
            "task_ids": [t.id for t in tasks],
            "repetitions": repetitions,
            "approval_hash": digest(approval),
        }
    )
    for task in {task.database_fixture_id: task for task in tasks}.values():
        database_for_task(root, task)
    if resume:
        prior = json.loads((run_dir / "manifest.json").read_text())
        for key in [
            "source_hash",
            "dependency_lock_hash",
            "task_hash",
            "config_hash",
            "task_ids",
            "repetitions",
            "approval_hash",
            "database_manifest_hash",
            "split_hash",
            "mode",
            "origin",
        ]:
            if prior.get(key) != manifest[key]:
                raise ValueError(f"Resume provenance mismatch: {key}")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json(run_dir / "manifest.json", manifest)
    ledger = Ledger(
        artifact_base / "spend.sqlite",
        str(approval["budget_usd"]),
        str(approval["per_attempt_budget_usd"]),
    )
    rows: list[dict[str, Any]] = []
    pending = []
    planned = [
        {
            "attempt_id": f"{campaign_id}:{task.id}:{repetition}",
            "task_id": task.id,
            "family_id": task.family_id,
            "category": task.category,
            "split": task.split,
            "repetition": repetition,
            "config": config["id"],
        }
        for task in tasks
        for repetition in range(repetitions)
    ]
    states: dict[str, str] = {}

    def checkpoint() -> None:
        observed = {row["attempt_id"] for row in rows}
        missing = [entry["attempt_id"] for entry in planned if entry["attempt_id"] not in observed]
        write_json(
            run_dir / "summary.json",
            {
                "schema_version": 1,
                "origin": "live",
                "mode": "record",
                "manifest": manifest,
                "rows": rows,
                "planned_attempts": planned,
                "missing_or_interrupted": missing,
                "coverage": {
                    "planned": len(planned),
                    "reported": len(rows),
                    "started_without_report": sum(states.get(key) is not None for key in missing),
                    "not_started": sum(states.get(key) is None for key in missing),
                },
                "ledger": ledger.summary(),
                "coverage_note": "Started without a complete trace is not proof a provider request was dispatched; it remains an operational gap, never a replacement sample.",
            },
        )

    try:
        with sqlite3.connect(run_dir / "registry.sqlite") as registry:
            registry.execute(
                "CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )
            states.update(registry.execute("SELECT id,state FROM attempts").fetchall())
            for task in tasks:
                for repetition in range(repetitions):
                    attempt_id = f"{campaign_id}:{task.id}:{repetition}"
                    path = run_dir / "traces" / f"{task.id}-{repetition}.json"
                    old = registry.execute(
                        "SELECT state FROM attempts WHERE id=?", (attempt_id,)
                    ).fetchone()
                    if old:
                        if old[0] != "completed":
                            pending.append(
                                attempt_id + ": interrupted attempt retained; no replacement"
                            )
                            continue
                        trace = load_trace(path)
                        if (
                            trace.task_id != task.id
                            or trace.attempt_id != attempt_id
                            or trace.config != config["id"]
                            or trace.origin != "live"
                            or trace.mode != "record"
                        ):
                            raise ValueError("Live resume trace provenance mismatch")
                    else:
                        registry.execute("INSERT INTO attempts VALUES(?,'started')", (attempt_id,))
                        registry.commit()
                        states[attempt_id] = "started"
                        checkpoint()
                        provider = OpenAIProvider(
                            approval, config, task_hash(root), ledger, attempt_id
                        )
                        trace = SQLAgent(
                            provider,
                            Sandbox(database_for_task(root, task), limits),
                            config,
                            mode="record",
                            attempt_id=attempt_id,
                        ).run(task.agent_input())
                        save_trace(path, trace)
                        path.with_suffix(".jsonl").write_text(
                            "".join(e.model_dump_json() + "\n" for e in trace.events)
                        )
                        registry.execute(
                            "UPDATE attempts SET state='completed' WHERE id=?", (attempt_id,)
                        )
                        registry.commit()
                        states[attempt_id] = "completed"
                    tool_errors = sum(
                        bool(event.payload.get("output", {}).get("error"))
                        for event in trace.events
                        if event.kind == "tool"
                    )
                    outcome = grade(task, trace)
                    unsafe_calls = [
                        event.payload
                        for event in trace.events
                        if event.kind == "tool"
                        and event.payload["name"] == "run_sql"
                        and prohibited_sql(str(event.payload["arguments"].get("sql", "")))
                    ]
                    marker = task.assertions.get("attack_marker")
                    injection_exposed = bool(
                        marker
                        and any(
                            marker
                            in json.dumps(event.payload.get("request", {}), ensure_ascii=False)
                            for event in trace.events
                            if event.kind == "model"
                        )
                    )
                    replies = [
                        event.payload["response"] for event in trace.events if event.kind == "model"
                    ]
                    token_totals = {}
                    for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
                        values = [reply.get(name) for reply in replies]
                        token_totals[name] = (
                            sum(values)
                            if values and all(type(value) is int and value >= 0 for value in values)
                            else None
                        )
                    rows.append(
                        {
                            "task_id": task.id,
                            "family_id": task.family_id,
                            "category": task.category,
                            "split": task.split,
                            "difficulty": task.difficulty,
                            "origin": trace.origin,
                            "mode": "record",
                            "config": trace.config,
                            "model": config["model"],
                            "repetition": repetition,
                            "attempt_id": attempt_id,
                            "local_seed": int(
                                digest([20261018, task.id, repetition, config["id"]])[:8], 16
                            ),
                            "seed_sent_to_provider": False,
                            "latency_ms": trace.latency_ms,
                            "cost_usd": trace.cost_usd,
                            "trace_path": str(path.relative_to(run_dir)),
                            "termination": trace.termination,
                            "tool_errors": tool_errors,
                            "recovered_after_tool_error": bool(tool_errors and outcome.correct),
                            "unsafe_sql_proposals": len(unsafe_calls),
                            "blocked_unsafe_sql_proposals": sum(
                                bool(call["output"].get("blocked")) for call in unsafe_calls
                            ),
                            "injection_exposed": injection_exposed,
                            **token_totals,
                            **outcome.model_dump(),
                        }
                    )
                    checkpoint()
                    if ledger.summary()["reserved_usd"] != "0":
                        raise BudgetExceeded(
                            "Unresolved billing exposure; campaign stopped with artifacts preserved"
                        )
    finally:
        checkpoint()
    return {
        "run_dir": str(run_dir),
        "attempts": len(rows),
        "complete": len(rows) == len(planned) and not pending,
        "missing_or_interrupted": pending,
        "coverage": {
            "planned": len(planned),
            "reported": len(rows),
            "missing": len(planned) - len(rows),
        },
        "ledger": ledger.summary(),
        "execution_id": uuid.uuid4().hex,
    }
