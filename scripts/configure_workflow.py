"""Create a local-only Compose credential file once; never replace credentials."""

import os
import secrets
from pathlib import Path

if __name__ == "__main__":
    path = Path(".env.workflow")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("ARH_WORKFLOW_DB_PASSWORD=" + secrets.token_hex(24) + "\n")
    print("Created .env.workflow; existing files are never replaced.")
