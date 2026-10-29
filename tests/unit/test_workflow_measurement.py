"""Check denominator retention and incomplete-pair suppression before experiments."""

import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

M = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/measure_workflow.py"))


def test_summary_keeps_failures_cancellations_and_never_admitted_in_denominators():
    now = datetime.now(UTC)
    jobs = [
        {
            "id": "ok",
            "state": "succeeded",
            "attempt_count": 1,
            "created_at": now,
            "finished_at": now + timedelta(seconds=2),
            "result": {"grade": {"correct": False}},
        },
        {
            "id": "failed",
            "state": "failed",
            "attempt_count": 3,
            "created_at": now,
            "finished_at": now + timedelta(seconds=3),
            "result": None,
        },
        {
            "id": "cancel",
            "state": "cancelled",
            "attempt_count": 0,
            "created_at": now,
            "finished_at": now + timedelta(seconds=1),
            "result": None,
        },
        {
            "id": "pending",
            "state": "queued",
            "attempt_count": 0,
            "created_at": now,
            "finished_at": None,
            "result": None,
        },
    ]
    attempts = [
        {
            "job_id": "ok",
            "number": 1,
            "state": "succeeded",
            "started_at": now + timedelta(seconds=0.5),
        }
    ]
    m = M["summarize"](jobs, attempts, [], {"reserved_units": 0, "spent_units": 0}, 6)
    assert m["terminal_coverage"] == 3 / 6
    assert m["succeeded_over_planned"] == 1 / 6
    assert m["never_admitted"] == 2 and m["nonterminal_jobs"] == 1
    assert m["extra_attempts"] == 2
    assert m["terminal_latency_seconds"]["count"] == 3
    assert m["fixture_grade"]["incorrect"] == 1


def test_uncertain_cost_stays_reserved_and_mismatch_is_visible():
    operations = [
        {"state": "uncertain", "reserved_units": 10, "actual_units": None},
        {"state": "succeeded", "reserved_units": 10, "actual_units": 6},
        {"state": "released", "reserved_units": 10, "actual_units": None},
    ]
    assert (
        M["summarize"]([], [], operations, {"reserved_units": 10, "spent_units": 6}, 12)[
            "budget_conservation_errors"
        ]
        == 0
    )
    assert (
        M["summarize"]([], [], operations, {"reserved_units": 0, "spent_units": 6}, 12)[
            "budget_conservation_errors"
        ]
        == 1
    )


def test_failed_batch_suppresses_paired_effect_instead_of_dropping_failure():
    batches = []
    for seed in [17, 29, 41]:
        for arm in ["no_fault", "worker_loss"]:
            batches.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "label": "VERIFIED",
                    "metrics": {
                        "terminal_latency_seconds": {"median": 1 if arm == "no_fault" else 2}
                    },
                }
            )
    complete = M["paired_analysis"](batches)
    assert complete["mean_paired_median_latency_difference_seconds"] == 1
    assert complete["exploratory_batch_bootstrap_ci95"] == [1, 1]
    batches[-1]["label"] = "FAILED"
    incomplete = M["paired_analysis"](batches)
    assert incomplete["effect"] is None and incomplete["incomplete_pairs"] == 1


def test_source_context_is_hash_bound_and_never_overwrites_an_existing_receipt(tmp_path):
    import hashlib
    import json
    import shutil
    import subprocess
    import sys

    project = Path(__file__).resolve().parents[2]
    root = tmp_path / "source-checkout"
    for name in (
        "scripts/workflow_source_context.py",
        "scripts/measure_workflow.py",
        "uv.lock",
        "experiments/workflow-stage3.v2.protocol.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, target)
    (root / "src").mkdir()
    (root / "src/fixture.py").write_text("# Synthetic source-context fixture\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Synthetic test fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Synthetic fixture only",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    path = tmp_path / "context.json"
    command = [
        sys.executable,
        str(root / "scripts/workflow_source_context.py"),
        "--output",
        str(path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    context = json.loads(path.read_text())
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert context["revision"] == revision
    assert context["dirty"] == ""
    assert (
        context["script_sha256"]
        == hashlib.sha256((root / "scripts/measure_workflow.py").read_bytes()).hexdigest()
    )
    assert (
        context["protocol_sha256"]
        == hashlib.sha256(
            (root / "experiments/workflow-stage3.v2.protocol.json").read_bytes()
        ).hexdigest()
    )
    before = path.read_bytes()
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    assert path.read_bytes() == before


def test_line_ending_repair_restores_exact_blob_but_preserves_real_changes(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    repair = runpy.run_path(str(root / "scripts/normalize_evidence.py"))["main"]
    repo = tmp_path / "fixture"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args], cwd=repo, capture_output=True, check=True
        )

    git("init", "-q")
    original = b'{\n  "unchanged": true\n}\n'
    evidence = repo / "evidence.json"
    changed = repo / "changed.json"
    evidence.write_bytes(original)
    changed.write_bytes(b'{"value": 1}\n')
    git("add", ".")
    git(
        "-c",
        "user.name=Synthetic test fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Synthetic fixture only",
    )
    evidence.write_bytes(original.replace(b"\n", b"\r\n"))
    user_change = b'{"value": 2}\r\n'
    changed.write_bytes(user_change)
    report = tmp_path / "repair.json"
    repair.__globals__["ROOT"] = repo
    monkeypatch.setattr(sys, "argv", ["normalize_evidence.py", "--fix", "--output", str(report)])
    with __import__("pytest").raises(SystemExit) as exit_info:
        repair()
    assert exit_info.value.code == 0
    assert evidence.read_bytes() == original
    assert changed.read_bytes() == user_change
    result = json.loads(report.read_text())
    assert result["left_changed_files"] == ["changed.json"]
    assert result["changes"][0]["normalized_sha256"] == result["changes"][0]["committed_sha256"]
