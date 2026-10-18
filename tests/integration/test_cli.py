import subprocess
import sys

from conftest import ROOT


def test_live_has_no_default_config_or_implicit_permission():
    result = subprocess.run(
        [sys.executable, "-m", "agent_reliability.cli", "eval-live"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--config" in result.stderr and "--approval" in result.stderr
