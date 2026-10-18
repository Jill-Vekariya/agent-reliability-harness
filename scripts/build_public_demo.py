"""Build the static synthetic trace walkthrough; no SQL or provider execution."""

import argparse
from pathlib import Path

from agent_reliability.reporting.public_demo import build

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    print(build(ROOT, parser.parse_args().output))
