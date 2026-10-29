"""Create local demo credentials once; never replace existing passwords or tokens."""

import argparse
import json
import os
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Add demo identity to an existing Stage 1 credential file",
    )
    args = parser.parse_args()
    env = Path(".env.workflow")
    auth = Path(".local/workflow-auth.json")
    if auth.exists() or (env.exists() and not args.auth_only):
        raise FileExistsError("Credentials already exist; never replace them")
    if args.auth_only and (not env.exists() or "ARH_WORKFLOW_AUTH_JSON=" in env.read_text()):
        raise ValueError(
            "Auth-only requires an existing Stage 1 credential file without auth configuration"
        )
    credentials = {
        secrets.token_urlsafe(32): {
            "tenant_id": "tenant-a",
            "subject": "submitter-a",
            "can_approve": False,
        },
        secrets.token_urlsafe(32): {
            "tenant_id": "tenant-a",
            "subject": "approver-a",
            "can_approve": True,
        },
        secrets.token_urlsafe(32): {
            "tenant_id": "tenant-b",
            "subject": "approver-b",
            "can_approve": True,
        },
    }
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth_fd = os.open(auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(auth_fd, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(credentials, stream, indent=2)
    flags = os.O_WRONLY | os.O_APPEND if args.auth_only else os.O_WRONLY | os.O_CREAT | os.O_EXCL
    env_fd = os.open(env, flags, 0o600)
    with os.fdopen(env_fd, "w", encoding="utf-8", newline="\n") as stream:
        if not args.auth_only:
            stream.write("ARH_WORKFLOW_DB_PASSWORD=" + secrets.token_hex(24) + "\n")
        stream.write(
            "\nARH_WORKFLOW_AUTH_JSON='" + json.dumps(credentials, separators=(",", ":")) + "'\n"
        )
    print("Created local demo identity; credentials were not printed or replaced.")


if __name__ == "__main__":
    main()
