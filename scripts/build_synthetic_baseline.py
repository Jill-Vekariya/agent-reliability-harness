"""Explicit bootstrap only. Normal evaluation cannot replace its own baseline."""

from pathlib import Path

from agent_reliability.runner import bootstrap_baseline

if __name__ == "__main__":
    baseline = bootstrap_baseline(Path(__file__).resolve().parents[1])
    print(
        f"Created SYNTHETIC engineering reference for {len(baseline['suite_ids'])} regression tasks. Human approval pending."
    )
