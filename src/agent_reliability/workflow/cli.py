"""Optional workflow imports are deferred so the offline CLI stays independent."""

import argparse
import json
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any


def add_commands(sub: Any) -> None:
    jobs = sub.add_parser("jobs", help="Local durable fixture jobs; install the workflow extra")
    commands = jobs.add_subparsers(dest="jobs_action", required=True)
    commands.add_parser("migrate")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8091)
    worker = commands.add_parser("worker")
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--effects", type=Path)
    submit = commands.add_parser("submit")
    submit.add_argument("--key", required=True)
    submit.add_argument("--task-id", default="q001")
    submit.add_argument(
        "--demo",
        choices=["none", "fail_once", "always_fail", "sleep", "effect", "provider"],
        default="none",
    )
    submit.add_argument("--delay-seconds", type=float, default=0.0)
    submit.add_argument("--require-approval", action="store_true")
    submit.add_argument(
        "--fake-usage", choices=["known", "missing_usage", "missing_price"], default="known"
    )
    submit.add_argument("--tenant", required=True, help="Trusted database operator scope")
    listing = commands.add_parser("list")
    listing.add_argument("--tenant", required=True)
    budget = commands.add_parser("set-budget", help="Operator-only synthetic credit limit")
    budget.add_argument("--tenant", required=True)
    budget.add_argument("--limit-units", type=int, required=True)
    for action in ("get", "attempts"):
        p = commands.add_parser(action)
        p.add_argument("job_id")
        p.add_argument("--tenant", required=True)


def run(args: argparse.Namespace, root: Path) -> None:
    try:
        from .models import JobRequest, Policy, database_url
        from .store import Store
    except ImportError as exc:
        raise ValueError(
            "Install optional workflow dependencies: uv sync --locked --extra workflow"
        ) from exc
    url = database_url()
    store = Store(url, Policy.from_env())
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.jobs_action == "migrate":
        from .migrations import migrate

        migrate(url)
        print('{"migration":"ready"}')
    elif args.jobs_action == "serve":
        import uvicorn

        from .api import create_app

        if args.host != "127.0.0.1" and os.environ.get("ARH_WORKFLOW_CONTAINER") != "1":
            raise ValueError(
                "Non-loopback binding is reserved for the isolated local Compose network"
            )
        uvicorn.run(
            create_app(root, store),
            host=args.host,
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )
    elif args.jobs_action == "worker":
        from .worker import run_worker

        stop = threading.Event()

        def stopping(signum: int, frame: Any) -> None:
            stop.set()

        signal.signal(signal.SIGTERM, stopping)
        signal.signal(signal.SIGINT, stopping)
        if not store.ready():
            raise ValueError("Migrate workflow database before starting a worker")
        run_worker(
            store,
            root,
            args.worker_id,
            args.effects or root / "artifacts/workflow-effects.sqlite",
            stop,
        )
    elif args.jobs_action == "set-budget":
        store.set_budget(args.tenant, args.limit_units)
        print(json.dumps(store.budget(args.tenant)))
    else:
        from fastapi.encoders import jsonable_encoder

        from .api import attempt_view, job_view
        from .catalog import resolved_payload

        if args.jobs_action == "submit":
            body = JobRequest(
                task_id=args.task_id,
                demo=args.demo,
                delay_seconds=args.delay_seconds,
                require_approval=args.require_approval,
                fake_usage=args.fake_usage,
            )
            row, created = store.submit(args.key, resolved_payload(root, body), args.tenant)
            result: Any = {"created": created, "job": job_view(row)}
        elif args.jobs_action == "list":
            result = [job_view(row) for row in store.list_jobs(tenant_id=args.tenant)]
        elif args.jobs_action == "get":
            found = store.get(args.job_id, args.tenant)
            result = job_view(found) if found else None
        else:
            result = [attempt_view(a) for a in store.attempts(args.job_id, args.tenant)]
        print(json.dumps(jsonable_encoder(result), indent=2))
