"""Human attestations and draft family splits. Neither function promotes a task."""

import json
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..models import EvaluationTask
from ..util import canonical, digest, file_hash, write_json
from .tasks import load_tasks, task_hash

REVIEW_FIELDS = {
    "task_id",
    "reviewer_id",
    "status",
    "review_date",
    "sql_correct",
    "expected_outcome_verified",
    "difficulty",
    "category",
    "clarification_needed",
    "notes",
}


def review_snapshots(tasks: list[EvaluationTask]) -> dict[str, Any]:
    # Administrative promotion/split assignment must not invalidate an otherwise
    # unchanged assessment. Final campaign freezes bind the full task/split hashes.
    return {
        task.id: task.model_dump(exclude={"reviewer", "review_status", "split"}) for task in tasks
    }


def review_packet(root: Path) -> dict[str, Any]:
    tasks = load_tasks(root)
    return {
        "schema_version": 1,
        "review_content_hash": digest(review_snapshots(tasks)),
        "database_manifest_hash": file_hash(root / "data/manifest.json"),
        "task_snapshots": review_snapshots(tasks),
        "reviews": [
            {
                "task_id": task.id,
                "reviewer_id": None,
                "status": "pending",
                "review_date": None,
                "sql_correct": None,
                "expected_outcome_verified": None,
                "difficulty": None,
                "category": None,
                "clarification_needed": None,
                "notes": "",
            }
            for task in tasks
        ],
        "adjudications": [],
        "notice": "Blank forms are not human reviews. Validation checks attestations, not a person's identity or whether they performed the work. Apply metadata only after maintainer review.",
    }


def check_reviews(root: Path, packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("Review packet must be an object")
    tasks = {task.id: task for task in load_tasks(root)}
    errors: list[str] = []
    if type(packet.get("schema_version")) is not int or packet["schema_version"] != 1:
        errors.append("Unsupported review packet version")
    if packet.get("review_content_hash") != digest(
        review_snapshots(list(tasks.values()))
    ) or packet.get("database_manifest_hash") != file_hash(root / "data/manifest.json"):
        errors.append("Stale task/database provenance; export a new packet")
    snapshots = packet.get("task_snapshots", {})
    if canonical(snapshots) != canonical(review_snapshots(list(tasks.values()))):
        errors.append("Task snapshots changed or coverage is incomplete")
    records = packet.get("reviews", [])
    if not isinstance(records, list):
        raise ValueError("reviews must be an array")
    accepted: dict[str, list[str]] = {}
    disputed: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != REVIEW_FIELDS:
            errors.append("Malformed review record")
            continue
        task_id = record["task_id"]
        task = tasks.get(task_id) if isinstance(task_id, str) else None
        if task is None:
            errors.append("Review names an unknown task")
            continue
        reviewer = record["reviewer_id"]
        state = record["status"]
        if not isinstance(state, str) or state not in {
            "pending",
            "accept",
            "needs_changes",
            "disputed",
        }:
            errors.append(f"{task.id}: invalid review status")
            continue
        if state == "pending":
            continue
        valid = True
        if not isinstance(reviewer, str) or not reviewer.strip():
            errors.append(f"{task.id}: reviewer identifier required")
            valid = False
        else:
            key = task.id, reviewer
            if key in seen:
                errors.append(f"{task.id}: duplicate reviewer record")
                valid = False
            seen.add(key)
        try:
            date.fromisoformat(record["review_date"])
        except (ValueError, TypeError):
            errors.append(f"{task.id}: ISO review date required")
            valid = False
        if state != "accept":
            disputed.add(task.id)
            continue
        if (
            (
                record["sql_correct"] is not True
                if task.gold_sql
                else record["sql_correct"] != "not_applicable"
            )
            or record["expected_outcome_verified"] is not True
            or record["difficulty"] != task.difficulty
            or record["category"] != task.category
            or type(record["clarification_needed"]) is not bool
            or record["clarification_needed"] != (task.expected_behavior == "clarify")
            or not isinstance(record["notes"], str)
            or not record["notes"].strip()
        ):
            errors.append(
                f"{task.id}: incomplete or disagreeing correctness/classification assessment"
            )
            valid = False
        if valid:
            accepted.setdefault(task.id, []).append(digest(record))
    unresolved = set(disputed)
    adjudications = packet.get("adjudications", [])
    if not isinstance(adjudications, list):
        raise ValueError("adjudications must be an array")
    for resolution in adjudications:
        if not isinstance(resolution, dict):
            errors.append("Malformed adjudication")
            continue
        task_id = resolution.get("task_id")
        if not isinstance(task_id, str):
            errors.append("Adjudication task identifier is required")
            continue
        try:
            raw_date = resolution.get("review_date")
            if not isinstance(raw_date, str):
                raise ValueError("Missing review date")
            date.fromisoformat(raw_date)
            dated = True
        except (ValueError, TypeError):
            dated = False
        if not (
            dated
            and isinstance(resolution.get("reviewer_id"), str)
            and resolution["reviewer_id"].strip()
            and isinstance(resolution.get("rationale"), str)
            and resolution["rationale"].strip()
            and resolution.get("accepted_review_sha256") in accepted.get(task_id, [])
        ):
            errors.append(
                "Adjudication needs an identified, dated rationale and accepted review hash"
            )
        else:
            unresolved.discard(task_id)
    completed = set(accepted) - unresolved
    pending = sorted(set(tasks) - completed)
    return {
        "schema_version": 1,
        "errors": errors,
        "attested_tasks": len(completed),
        "pending_task_ids": pending,
        "unresolved_disagreements": sorted(unresolved),
        "ready_for_metadata_review": not errors and not pending,
        "human_identity_independently_verified": False,
        "task_metadata_modified": False,
    }


def normalized_question(question: str) -> str:
    return " ".join(re.findall(r"\w+", question.casefold()))


def sql_template(task: EvaluationTask) -> str | None:
    if not task.gold_sql:
        return None
    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(task.gold_sql, read="sqlite")
    # Literals distinguish task instances, not leakage-resistant query families.
    tree = tree.transform(
        lambda node: exp.Literal.string("?") if isinstance(node, exp.Literal) else node
    )
    return tree.sql(dialect="sqlite", normalize=True)


def near_duplicates(tasks: list[EvaluationTask]) -> list[dict[str, Any]]:
    signatures = {task.id: sql_template(task) for task in tasks}
    pairs = []
    for index, left in enumerate(tasks):
        for right in tasks[index + 1 :]:
            text_ratio = SequenceMatcher(
                None, normalized_question(left.question), normalized_question(right.question)
            ).ratio()
            same_sql = (
                signatures[left.id] is not None and signatures[left.id] == signatures[right.id]
            )
            if text_ratio >= 0.88 or same_sql:
                pairs.append(
                    {
                        "left": left.id,
                        "right": right.id,
                        "reason": "same_sql_template" if same_sql else "similar_question",
                        "text_similarity": round(text_ratio, 4),
                    }
                )
    return pairs


def grouped_split(
    root: Path, *, seed: int = 20261018, test_fraction: float = 0.4
) -> dict[str, Any]:
    if type(seed) is not int:
        raise ValueError("Split seed must be an integer")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be strictly between zero and one")
    tasks = load_tasks(root)
    ids = {task.id for task in tasks}
    exposure_path = root / "tasks/development_exposure.json"
    exposure = json.loads(exposure_path.read_text())
    protected = set(exposure["task_ids"])
    if not protected <= ids:
        raise ValueError("Exposure history refers to missing tasks; resolve history explicitly")
    parents = {task.id: task.id for task in tasks}

    def find(key: str) -> str:
        while parents[key] != key:
            key = parents[key]
        return key

    def join(left: str, right: str) -> None:
        a, b = find(left), find(right)
        parents[max(a, b)] = min(a, b)

    families: dict[str, str] = {}
    for task in tasks:
        if task.family_id in families:
            join(task.id, families[task.family_id])
        families[task.family_id] = task.id
    duplicates = near_duplicates(tasks)
    for pair in duplicates:
        join(pair["left"], pair["right"])
    groups: dict[str, list[str]] = {}
    for task in tasks:
        groups.setdefault(find(task.id), []).append(task.id)
    assignments = dict.fromkeys(sorted(ids), "dev")
    diagnostic = {task.id for task in tasks if task.category == "clarification"}
    target = round((len(tasks) - len(diagnostic)) * test_fraction)
    selected = 0
    for group in sorted(groups.values(), key=lambda items: digest([seed, sorted(items)])):
        if protected.intersection(group) or diagnostic.intersection(group):
            continue
        if abs(selected + len(group) - target) < abs(selected - target):
            for key in group:
                assignments[key] = "test"
            selected += len(group)
    return {
        "schema_version": 1,
        "status": "proposal_not_frozen",
        "frozen": False,
        "seed": seed,
        "grouping_rule": "declared families plus SQL-template/text-similarity components v1",
        "task_hash": task_hash(root),
        "database_manifest_hash": file_hash(root / "data/manifest.json"),
        "exposure_history_hash": file_hash(exposure_path),
        "dataset_versions": sorted({task.dataset_version for task in tasks}),
        "development_exposed_ids": sorted(protected),
        "assignments": assignments,
        "groups": sorted([sorted(group) for group in groups.values()]),
        "near_duplicate_candidates": duplicates,
        "requested_test_fraction": test_fraction,
        "target_test_count": target,
        "actual_test_count": selected,
        "eligible_for_headline": False,
        "blockers": [
            "Human review, maintainer split review, and a separately frozen experiment remain required"
        ]
        + (
            ["No unexposed task family is available for test; add genuinely new families"]
            if selected == 0
            else []
        ),
    }


def check_grouped_split(root: Path, manifest: dict[str, Any]) -> list[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assignments"), dict):
        return ["Split manifest and assignments must be objects"]
    tasks = load_tasks(root)
    assignments = manifest.get("assignments", {})
    errors = []
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("Unsupported split version")
    if set(assignments) != {task.id for task in tasks} or any(
        value not in {"dev", "test"} for value in assignments.values()
    ):
        errors.append("Split coverage/labels invalid")
    if manifest.get("task_hash") != task_hash(root) or manifest.get(
        "database_manifest_hash"
    ) != file_hash(root / "data/manifest.json"):
        errors.append("Split provenance changed")
    if manifest.get("exposure_history_hash") != file_hash(root / "tasks/development_exposure.json"):
        errors.append("Exposure history changed")
    canonical_plan = grouped_split(
        root,
        seed=manifest.get("seed", 20261018),
        test_fraction=manifest.get("requested_test_fraction", 0.4),
    )
    for name in ("groups", "development_exposed_ids", "dataset_versions", "grouping_rule"):
        if manifest.get(name) != canonical_plan[name]:
            errors.append("Split grouping metadata changed: " + name)
    if manifest.get("actual_test_count") != sum(value == "test" for value in assignments.values()):
        errors.append("Split count does not match assignments")
    for group in canonical_plan["groups"]:
        if len({assignments.get(key) for key in group}) != 1:
            errors.append("Family or near-duplicate leakage: " + ",".join(group))
    for key in canonical_plan["development_exposed_ids"]:
        if assignments.get(key) != "dev":
            errors.append("Development-exposed task assigned to test: " + key)
    return errors


def export_review(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Review packet already exists; preserve completed human work")
    write_json(output, review_packet(root))
