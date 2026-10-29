"""Bind jobs to trusted task/fixture inputs; the API accepts no SQL or paths."""

import json
from pathlib import Path
from typing import Any

from ..evaluation.tasks import database_for_task, load_tasks
from ..models import Limits
from ..util import digest, file_hash
from .models import JobRequest


def resolved_payload(root: Path, request: JobRequest) -> dict[str, Any]:
    tasks = {task.id: task for task in load_tasks(root)}
    task = tasks.get(request.task_id)
    if task is None or task.split != "dev":
        raise ValueError("Unknown development fixture task")
    scripts = json.loads(
        (root / "tests/fixtures/provider_scripts.json").read_text(encoding="utf-8")
    )["scripts"]
    if request.task_id not in scripts:
        raise ValueError("Missing synthetic fixture script")
    return {
        "request": request.model_dump(),
        "provenance": {
            "task": digest(task.model_dump()),
            "script": digest(scripts[request.task_id]),
            "database": file_hash(database_for_task(root, task)),
            "limits": Limits().model_dump(),
            "adapter_version": 1,
            "source": digest(
                {
                    p.relative_to(root).as_posix(): file_hash(p)
                    for p in sorted((root / "src").rglob("*.py"))
                }
            ),
            "dependency_lock": file_hash(root / "uv.lock"),
        },
    }
