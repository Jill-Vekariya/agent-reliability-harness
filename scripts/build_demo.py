import json
import shutil
from pathlib import Path

from agent_reliability.agents import SQLAgent
from agent_reliability.evaluation.tasks import load_tasks
from agent_reliability.providers.fixture import FixtureProvider
from agent_reliability.runner import run_offline
from agent_reliability.sandbox import Sandbox
from agent_reliability.tracing.recording import save_trace
from agent_reliability.util import write_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    summary = run_offline(ROOT, all_tasks=True)
    source = Path(summary["run_dir"])
    destination = ROOT / "demo"
    destination.mkdir(exist_ok=True)
    shutil.copytree(source / "traces", destination / "traces", dirs_exist_ok=True)
    summary["run_dir"] = "demo"
    write_json(destination / "summary.json", summary)
    task = next(t for t in load_tasks(ROOT) if t.id == "q002")
    script = json.loads((ROOT / "tests/fixtures/provider_scripts.json").read_text())["scripts"][
        "q002"
    ]
    script[-1]["arguments"]["result_id"] = "r002"
    config = {"id": "synthetic-recovery-walkthrough", "retry_on_error": 1}
    trace = SQLAgent(
        FixtureProvider(script),
        Sandbox(ROOT / "data/chinook.sqlite"),
        config,
        attempt_id="synthetic-recovery-q002",
    ).run(task.agent_input())
    assert trace.final and trace.final["status"] == "answered"
    save_trace(destination / "recovery.json", trace)
    print(
        "Built portable SYNTHETIC demo with baseline/recovery walkthrough. No measured tradeoff is implied."
    )


if __name__ == "__main__":
    main()
