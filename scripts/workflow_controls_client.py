"""Credential-file client for the loopback-only Stage 2 demonstration."""

import argparse
import http.client
import json
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=Path(".local/workflow-auth.json"))
    parser.add_argument("--subject", default="submitter-a")
    parser.add_argument("--port", type=int, default=8091)
    commands = parser.add_subparsers(dest="action", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--key", required=True)
    submit.add_argument(
        "--demo", choices=["none", "provider", "effect", "sleep"], default="provider"
    )
    submit.add_argument("--delay-seconds", type=float, default=0)
    submit.add_argument(
        "--fake-usage", choices=["known", "missing_usage", "missing_price"], default="known"
    )
    for action in ["jobs", "approvals", "budget"]:
        commands.add_parser(action)
    for action in ["get", "result", "trace", "operations", "cancel"]:
        child = commands.add_parser(action)
        child.add_argument("job_id", type=uuid.UUID)
    decide = commands.add_parser("decide")
    decide.add_argument("approval_id", type=uuid.UUID)
    decide.add_argument("--decision", required=True, choices=["approved", "rejected"])
    decide.add_argument("--action-hash", required=True)
    decide.add_argument("--action-version", required=True, type=int)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid loopback port")
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    tokens = [
        token for token, identity in credentials.items() if identity["subject"] == args.subject
    ]
    if len(tokens) != 1:
        parser.error("Subject must select exactly one configured local demo identity")
    method, body = "GET", None
    if args.action == "submit":
        path, method = "/jobs", "POST"
        body = {
            "demo": args.demo,
            "delay_seconds": args.delay_seconds,
            "fake_usage": args.fake_usage,
        }
    elif args.action == "decide":
        path, method = f"/approvals/{args.approval_id}/decision", "POST"
        body = {
            "decision": args.decision,
            "action_hash": args.action_hash,
            "action_version": args.action_version,
        }
    elif args.action in {"jobs", "approvals", "budget"}:
        path = "/" + args.action
    else:
        path = f"/jobs/{args.job_id}" + ("" if args.action == "get" else "/" + args.action)
        if args.action == "cancel":
            method = "POST"
    headers = {"Authorization": "Bearer " + tokens[0], "Content-Type": "application/json"}
    if args.action == "submit":
        headers["Idempotency-Key"] = args.key
    # Fixed loopback host, no proxy support and no redirect following: never forward a token.
    conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=3)
    try:
        conn.request(
            method, path, body=json.dumps(body) if body is not None else None, headers=headers
        )
        response = conn.getresponse()
        print(
            json.dumps({"status": response.status, "body": json.loads(response.read())}, indent=2)
        )
        raise SystemExit(0 if response.status < 400 else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
