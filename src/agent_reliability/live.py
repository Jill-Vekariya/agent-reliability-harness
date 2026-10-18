"""Fresh campaign execution. No invocation is authorized by the bundled templates."""

import json
import os
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from .agents import SQLAgent
from .evaluation.grading import grade
from .evaluation.tasks import database_for_task, load_tasks, task_hash
from .models import Limits
from .providers.budget import BudgetExceeded, Ledger
from .providers.openai_adapter import OpenAIProvider, read_approval, validate_approval
from .runner import environment_manifest
from .sandbox import Sandbox
from .tracing.recording import load_trace, save_trace
from .util import digest, write_json


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
        freeze_path = root / "experiments/freeze.json"
        if (
            not freeze_path.exists()
            or any(t.review_status != "human_reviewed" for t in load_tasks(root))
            or repetitions != 5
        ):
            raise BudgetExceeded(
                "Headline test campaign requires reviewed corpus, freeze manifest, and five fresh attempts"
            )
        freeze = json.loads(freeze_path.read_text())
        if freeze.get("task_hash") != task_hash(root) or digest(config) not in freeze.get(
            "config_hashes", []
        ):
            raise BudgetExceeded("Frozen task/configuration hashes do not match")
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
        ]:
            if prior[key] != manifest[key]:
                raise ValueError(f"Resume provenance mismatch: {key}")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json(run_dir / "manifest.json", manifest)
    ledger = Ledger(
        artifact_base / "spend.sqlite",
        str(approval["budget_usd"]),
        str(approval["per_attempt_budget_usd"]),
    )
    rows = []
    pending = []
    with sqlite3.connect(run_dir / "registry.sqlite") as registry:
        registry.execute(
            "CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, state TEXT NOT NULL)"
        )
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
                else:
                    registry.execute("INSERT INTO attempts VALUES(?,'started')", (attempt_id,))
                    registry.commit()
                    provider = OpenAIProvider(approval, config, task_hash(root), ledger, attempt_id)
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
                        "repetition": repetition,
                        "attempt_id": attempt_id,
                        "local_seed": int(
                            digest([20261018, task.id, repetition, config["id"]])[:8], 16
                        ),
                        "seed_sent_to_provider": False,
                        "latency_ms": trace.latency_ms,
                        "cost_usd": trace.cost_usd,
                        "trace_path": str(path.relative_to(run_dir)),
                        **grade(task, trace).model_dump(),
                    }
                )
                write_json(
                    run_dir / "summary.json",
                    {
                        "schema_version": 1,
                        "rows": rows,
                        "missing_or_interrupted": pending,
                        "ledger": ledger.summary(),
                    },
                )
                if ledger.summary()["reserved_usd"] != "0":
                    raise BudgetExceeded(
                        "Unresolved billing exposure; campaign stopped with artifacts preserved"
                    )
    return {
        "run_dir": str(run_dir),
        "attempts": len(rows),
        "missing_or_interrupted": pending,
        "ledger": ledger.summary(),
        "execution_id": uuid.uuid4().hex,
    }
