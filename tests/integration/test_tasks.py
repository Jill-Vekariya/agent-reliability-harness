import shutil

import yaml
from conftest import ROOT

from agent_reliability.evaluation.tasks import lint_tasks


def test_candidates_and_lint_detect_stale_gold_and_split_leakage(tmp_path):
    assert lint_tasks(ROOT) == []
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copytree(ROOT / "tasks", tmp_path / "tasks")
    p = tmp_path / "tasks/normal/candidates.yaml"
    tasks = yaml.safe_load(p.read_text())
    tasks[0]["expected_result"] = [[999]]
    tasks[2]["split"] = "test"
    p.write_text(yaml.safe_dump(tasks))
    errors = lint_tasks(tmp_path)
    assert any("Stale expected" in x for x in errors)
    assert any("Family leakage" in x for x in errors)
    assert any("Split manifest" in x for x in errors)
