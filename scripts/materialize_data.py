"""Acquire only the pinned snapshot; reconstruct the exact bundled attack fixture."""

import base64
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    database = ROOT / "data/chinook.sqlite"
    if not database.exists():
        with urllib.request.urlopen(manifest["source_url"], timeout=60) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000 or sha(raw) != manifest["download_sha256"]:
            raise RuntimeError("Downloaded snapshot failed its size/checksum check")
        database.write_bytes(raw)
    if sha(database.read_bytes()) != manifest["database_sha256"]:
        raise RuntimeError("Existing database differs from pinned data; it was not overwritten")
    patch = json.loads((ROOT / "data/fixtures/injection.patch.json").read_text())
    fixture = ROOT / "data/fixtures/injection.sqlite"
    if not fixture.exists():
        data = bytearray(database.read_bytes())
        for entry in patch["segments"]:
            offset = entry["offset"]
            replacement = base64.b64decode(entry["bytes"])
            if offset < 0 or offset + len(replacement) > len(data):
                raise RuntimeError("Invalid fixture patch")
            data[offset : offset + len(replacement)] = replacement
        if sha(data) != manifest["fixtures"]["injection-v1"]["sha256"]:
            raise RuntimeError("Reconstructed fixture checksum mismatch")
        fixture.write_bytes(data)
    if sha(fixture.read_bytes()) != manifest["fixtures"]["injection-v1"]["sha256"]:
        raise RuntimeError("Existing diagnostic fixture was changed; it was not overwritten")
    print("Pinned database and exact diagnostic fixture verified.")


if __name__ == "__main__":
    main()
