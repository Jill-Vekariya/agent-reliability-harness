from pathlib import Path

import pytest

from agent_reliability.sandbox import Sandbox

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sandbox():
    return Sandbox(ROOT / "data/chinook.sqlite")
