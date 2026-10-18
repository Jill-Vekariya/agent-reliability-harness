import copy
import json
import shutil

import pytest
import yaml
from conftest import ROOT
from pydantic import ValidationError

from agent_reliability.evaluation.review import (
    check_grouped_split,
    check_reviews,
    export_review,
    grouped_split,
    review_packet,
)
from agent_reliability.evaluation.tasks import load_tasks, task_hash
from agent_reliability.models import EvaluationTask
from agent_reliability.util import digest


def accepted_form(packet):
    form = copy.deepcopy(packet["reviews"][0])
    task = packet["task_snapshots"][form["task_id"]]
    form.update(
        reviewer_id="SYNTHETIC_UNIT_TEST_ONLY",
        status="accept",
        review_date="2026-10-18",
        sql_correct=True,
        expected_outcome_verified=True,
        difficulty=task["difficulty"],
        category=task["category"],
        clarification_needed=False,
        notes="Simulated assessment for validation tests; no real human review.",
    )
    return form


def test_blank_packet_preserves_pending_status_and_existing_work(tmp_path):
    before = task_hash(ROOT)
    output = tmp_path / "review.json"
    export_review(ROOT, output)
    result = check_reviews(ROOT, json.loads(output.read_text()))
    assert result["errors"] == [] and result["attested_tasks"] == 0
    assert len(result["pending_task_ids"]) == 37 and not result["ready_for_metadata_review"]
    with pytest.raises(ValueError, match="already exists"):
        export_review(ROOT, output)
    assert task_hash(ROOT) == before
    assert all(
        task.review_status == "candidate" and task.reviewer is None for task in load_tasks(ROOT)
    )


def test_review_requires_correctness_identity_date_and_current_snapshot():
    packet = review_packet(ROOT)
    form = accepted_form(packet)
    packet["reviews"].append(form)
    assert check_reviews(ROOT, packet)["attested_tasks"] == 1
    for field, invalid in (
        ("sql_correct", 1),
        ("reviewer_id", None),
        ("review_date", None),
        ("expected_outcome_verified", False),
    ):
        altered = copy.deepcopy(packet)
        altered["reviews"][-1][field] = invalid
        result = check_reviews(ROOT, altered)
        assert result["errors"] and not result["ready_for_metadata_review"]
    packet["task_snapshots"][form["task_id"]]["expected_result"] = [[999]]
    assert any("snapshots" in error for error in check_reviews(ROOT, packet)["errors"])


def test_disagreement_requires_provenance_bound_adjudication():
    packet = review_packet(ROOT)
    form = accepted_form(packet)
    packet["reviews"] += [
        form,
        {**form, "reviewer_id": "SECOND_SYNTHETIC_TEST", "status": "disputed"},
    ]
    result = check_reviews(ROOT, packet)
    assert result["attested_tasks"] == 0 and result["unresolved_disagreements"]
    packet["adjudications"] = [
        {
            "task_id": form["task_id"],
            "reviewer_id": "SYNTHETIC_ADJUDICATOR",
            "review_date": "2026-10-18",
            "rationale": "Synthetic resolution fixture",
            "accepted_review_sha256": digest(form),
        }
    ]
    result = check_reviews(ROOT, packet)
    assert result["attested_tasks"] == 1 and not result["unresolved_disagreements"]
    assert not result["human_identity_independently_verified"]


def test_administrative_promotion_does_not_invalidate_unchanged_gold_review(tmp_path):
    shutil.copytree(ROOT / "tasks", tmp_path / "tasks")
    shutil.copytree(ROOT / "data", tmp_path / "data")
    packet = review_packet(tmp_path)
    packet["reviews"].append(accepted_form(packet))
    path = tmp_path / "tasks/normal/candidates.yaml"
    candidates = yaml.safe_load(path.read_text())
    candidates[0].update(review_status="human_reviewed", reviewer="SYNTHETIC_UNIT_TEST_ONLY")
    path.write_text(yaml.safe_dump(candidates))
    assert check_reviews(tmp_path, packet)["errors"] == []
    candidates[0]["expected_result"] = [[999]]
    path.write_text(yaml.safe_dump(candidates))
    assert check_reviews(tmp_path, packet)["errors"]


def test_committed_packets_remain_blank_current_and_development_only():
    packet = json.loads((ROOT / "reviews/benchmark-candidates.json").read_text())
    result = check_reviews(ROOT, packet)
    assert result["errors"] == [] and result["attested_tasks"] == 0
    split = json.loads((ROOT / "tasks/grouped-split.proposal.json").read_text())
    assert check_grouped_split(ROOT, split) == [] and split["actual_test_count"] == 0


def test_public_development_tasks_cannot_be_rebranded_as_holdout():
    first = grouped_split(ROOT)
    assert first == grouped_split(ROOT)
    assert first["actual_test_count"] == 0 and not first["frozen"]
    assert not first["eligible_for_headline"] and check_grouped_split(ROOT, first) == []
    first["assignments"]["q001"] = "test"
    assert any("exposed" in error for error in check_grouped_split(ROOT, first))


def test_new_private_family_can_be_proposed_without_changing_current_split(tmp_path):
    shutil.copytree(ROOT / "tasks", tmp_path / "tasks")
    shutil.copytree(ROOT / "data", tmp_path / "data")
    original_split = (tmp_path / "tasks/splits.json").read_bytes()
    original = load_tasks(ROOT)[0].model_dump()
    new = [
        {
            **original,
            "id": "private_fixture_a",
            "family_id": "private_a",
            "question": "Synthetic private constant seven",
            "gold_sql": "SELECT 7 AS n",
            "expected_columns": ["n"],
            "expected_result": [[7]],
            "source": "SYNTHETIC TEST ONLY",
        },
        {
            **original,
            "id": "private_fixture_b",
            "family_id": "private_b",
            "question": "A second synthetic constant eight",
            "gold_sql": "SELECT 8 AS n",
            "expected_columns": ["n"],
            "expected_result": [[8]],
            "source": "SYNTHETIC TEST ONLY",
        },
    ]
    (tmp_path / "tasks/private.yaml").write_text(yaml.safe_dump(new))
    proposal = grouped_split(tmp_path)
    assert (
        proposal["assignments"]["private_fixture_a"]
        == proposal["assignments"]["private_fixture_b"]
        == "test"
    )
    assert check_grouped_split(tmp_path, proposal) == []
    assert (tmp_path / "tasks/splits.json").read_bytes() == original_split


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../escape"),
        ("schema_version", 2),
        ("expected_result", None),
        ("tolerant_columns", [-1]),
        ("difficulty", "unknown"),
    ],
)
def test_task_schema_rejects_invalid_candidates(field, value):
    data = load_tasks(ROOT)[0].model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        EvaluationTask.model_validate(data)
