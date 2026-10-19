import json
from pathlib import Path

import yaml

from ..models import EvaluationTask
from ..sandbox import Sandbox
from ..util import digest
from .grading import compare_rows


def database_for_task(root: Path, task: EvaluationTask) -> Path:
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    if task.database_fixture_id == manifest["dataset_id"]:
        path, expected = root / "data/chinook.sqlite", manifest["database_sha256"]
    else:
        fixture = manifest["fixtures"][task.database_fixture_id]
        path, expected = root / fixture["path"], fixture["sha256"]
    from ..util import file_hash

    if file_hash(path) != expected:
        raise ValueError("Database fixture checksum mismatch")
    return path


def load_tasks(root: Path) -> list[EvaluationTask]:
    tasks: list[EvaluationTask] = []
    for path in sorted((root / "tasks").rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"Expected a task list: {path}")
        tasks.extend(EvaluationTask.model_validate(item) for item in raw)
    return tasks


def lint_tasks(root: Path) -> list[str]:
    tasks = load_tasks(root)
    sandbox = Sandbox(root / "data/chinook.sqlite")
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    if (
        __import__("hashlib").sha256(sandbox.database.read_bytes()).hexdigest()
        != manifest["database_sha256"]
    ):
        return ["Database checksum mismatch"]
    errors: list[str] = []
    ids: set[str] = set()
    questions: set[str] = set()
    families: dict[str, str] = {}
    splits = json.loads((root / "tasks/splits.json").read_text(encoding="utf-8"))["assignments"]
    for task in tasks:
        if task.id in ids:
            errors.append(f"Duplicate ID: {task.id}")
        ids.add(task.id)
        question = " ".join(task.question.casefold().split())
        if question in questions:
            errors.append(f"Duplicate question: {task.id}")
        questions.add(question)
        if task.family_id in families and families[task.family_id] != task.split:
            errors.append(f"Family leakage: {task.family_id}")
        families[task.family_id] = task.split
        if splits.get(task.id) != task.split:
            errors.append(f"Split manifest mismatch: {task.id}")
        if not task.source or not task.authoring_method:
            errors.append(f"Missing provenance: {task.id}")
        if task.gold_sql:
            result = Sandbox(database_for_task(root, task)).run(task.gold_sql)
            if not result.ok or result.truncated:
                errors.append(f"Gold SQL failed or truncated: {task.id}: {result.error}")
            elif result.columns != task.expected_columns or not compare_rows(
                result.rows,
                task.expected_result or [],
                ordered=task.ordered,
                atol=task.atol,
                rtol=task.rtol,
                tolerant_columns=task.tolerant_columns,
            ):
                errors.append(f"Stale expected result: {task.id}")
        if task.category != "ordinary" and not task.assertions:
            errors.append(f"Missing safety assertions: {task.id}")
    if set(splits) != ids:
        errors.append("Split manifest has missing/extra task IDs")
    return errors


def task_hash(root: Path) -> str:
    return digest([t.model_dump() for t in load_tasks(root)])
