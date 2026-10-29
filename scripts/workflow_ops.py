"""Local Compose operations with private backups and fresh-target-only restore.

No public deployment, live provider access, volume deletion or secret printing.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def credentials(root: Path) -> dict[str, str]:
    """Parse only the generator's dotenv format; never evaluate shell content."""
    from agent_reliability.workflow.auth import DemoAuth, Principal

    values = {}
    for line in (root / ".env.workflow").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in values or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("Malformed or duplicate local configuration key")
        values[key] = value.removeprefix("'").removesuffix("'")
    password = values.get("ARH_WORKFLOW_DB_PASSWORD", "")
    if not re.fullmatch(r"[a-f0-9]{48}", password):
        raise ValueError("Generate a random local DB password with configure_workflow.py")
    mapping = json.loads(values.get("ARH_WORKFLOW_AUTH_JSON", "{}"))
    DemoAuth({token: Principal(**identity) for token, identity in mapping.items()})
    if not (root / ".local/workflow-auth.json").is_file():
        raise ValueError("Generated private auth file is missing")
    if json.loads((root / ".local/workflow-auth.json").read_text()) != mapping:
        raise ValueError("Private auth file disagrees with Compose credentials")
    return values


class Ops:
    def __init__(self, project: str, root: Path = ROOT, *, image: str | None = None) -> None:
        if not re.fullmatch(r"arh-[a-z0-9][a-z0-9-]{1,50}", project):
            raise ValueError("Explicit arh- project name required")
        self.root, self.project = root, project
        self.env = {**os.environ, **credentials(root)}
        if image:
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                raise ValueError("Select an immutable local image ID")
            self.env["ARH_WORKFLOW_IMAGE"] = image
        self.prefix = [
            "docker",
            "compose",
            "--env-file",
            ".env.workflow",
            "-f",
            "compose.workflow.yaml",
            "-p",
            project,
        ]

    def command(
        self,
        args: list[str],
        *,
        timeout: int = 120,
        input_stream: BinaryIO | None = None,
        output_stream: BinaryIO | None = None,
    ) -> bytes:
        # Errors are classified without reproducing command output/configuration,
        # which can contain credentials. Raw stderr is kept out of public receipts.
        result = subprocess.run(
            args,
            cwd=self.root,
            env=self.env,
            stdin=input_stream,
            stdout=output_stream or subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(
                f"Local operation failed (exit {result.returncode}); operation={args[0]}"
            )
        return result.stdout or b""

    def compose(self, *args: str, **kwargs: Any) -> bytes:
        return self.command([*self.prefix, *args], **kwargs)

    def inspect(self, image: str) -> dict[str, Any]:
        return json.loads(self.command(["docker", "image", "inspect", image]))[0]

    def image(self) -> str:
        return self.inspect(self.env.get("ARH_WORKFLOW_IMAGE", "arh-workflow:stage5-local"))["Id"]

    def validate(self) -> dict[str, Any]:
        config = json.loads(self.compose("config", "--format", "json"))
        services = config["services"]
        ports = services["api"].get("ports", [])
        if (
            not ports
            or any(p.get("host_ip") != "127.0.0.1" for p in ports)
            or services["workflow-db"].get("ports")
            or not config["networks"]["workflow"].get("internal")
            or any(
                services[s]["environment"].get("API_BUDGET_USD") != "0"
                or services[s]["environment"].get("ARH_WORKFLOW_MODE") != "local"
                for s in ("api", "worker-a", "worker-b")
            )
        ):
            raise ValueError("Local exposure, isolation or zero-spend configuration violated")
        return {"configuration": "valid", "mode": "local-synthetic", "credentials_printed": False}

    def schema(self, image: str) -> dict[str, str]:
        code = (
            "import json,hashlib,pathlib;from agent_reliability.workflow import migrations;"
            "p=pathlib.Path(migrations.__file__).with_name('sql');"
            "print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.sql')}))"
        )
        return json.loads(
            self.command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    image,
                    "python",
                    "-c",
                    code,
                ]
            )
        )

    def state(self) -> dict[str, Any]:
        code = "SELECT json_object_agg(version,sha256) FROM workflow_schema_migrations"
        result = self.compose(
            "exec",
            "-T",
            "workflow-db",
            "psql",
            "-U",
            "arh",
            "-d",
            "arh_workflow",
            "-A",
            "-t",
            "-c",
            code,
        ).strip()
        return json.loads(result)

    def fresh(self) -> None:
        for kind, flags in [("ps", ["-a", "-q"]), ("volume", ["ls", "-q"])]:
            found = self.command(
                [
                    "docker",
                    kind,
                    *flags,
                    "--filter",
                    f"label=com.docker.compose.project={self.project}",
                ]
            )
            if found.strip():
                raise ValueError(
                    "Restore refuses existing project containers or persistent volumes"
                )

    def postgres_version(self) -> int:
        return int(
            self.compose(
                "exec",
                "-T",
                "workflow-db",
                "psql",
                "-U",
                "arh",
                "-d",
                "arh_workflow",
                "-A",
                "-t",
                "-c",
                "SHOW server_version_num",
            ).strip()
        )

    def wait_database(self) -> None:
        for _ in range(45):
            try:
                self.compose(
                    "exec",
                    "-T",
                    "workflow-db",
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "arh",
                    "-d",
                    "arh_workflow",
                    timeout=4,
                )
                return
            except RuntimeError:
                time.sleep(1)
        raise RuntimeError("Database startup deadline exceeded")

    def backup(self, output: Path) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        ids = self.compose("ps", "--all", "-q", "api", "worker-a", "worker-b").decode().split()
        if not ids:
            raise ValueError("Backup requires an existing deployed application")
        images = {c["Image"] for c in json.loads(self.command(["docker", "inspect", *ids]))}
        if len(images) != 1:
            raise ValueError("Application containers disagree on image identity")
        image = next(iter(images))
        self.env["ARH_WORKFLOW_IMAGE"] = image
        running = self.compose("ps", "--status", "running", "--services").decode().split()
        if set(running) - {"workflow-db", "api", "worker-a", "worker-b"}:
            raise ValueError("Stop other task writers/checks before coordinated backup")
        self.compose("stop", "api", "worker-a", "worker-b")
        # Remain stopped if backup fails. Do not obscure the failure by restarting.
        schema = self.state()
        if schema != self.schema(image):
            raise ValueError("Running image/schema mismatch; backup is not a rollback boundary")
        dump, reports = output / "workflow.dump", output / "reports.tar"
        for path, command in [
            (
                dump,
                [
                    "exec",
                    "-T",
                    "workflow-db",
                    "pg_dump",
                    "-U",
                    "arh",
                    "-d",
                    "arh_workflow",
                    "-Fc",
                    "--no-owner",
                    "--no-acl",
                ],
            ),
            (
                reports,
                [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "--entrypoint",
                    "python",
                    "worker-a",
                    "-m",
                    "agent_reliability.workflow.snapshot",
                    "create",
                ],
            ),
        ]:
            with path.open("xb") as stream:
                self.compose(*command, output_stream=stream)
            path.chmod(0o600)
        result = {
            "schema_version": 1,
            "project": self.project,
            "image_id": image,
            "migrations": schema,
            "postgres_version_num": self.postgres_version(),
            "files": {p.name: sha(p) for p in (dump, reports)},
            "created_at_epoch": time.time(),
            "writers_stopped": True,
            "scope": "Coordinated local PostgreSQL state and report/synthetic-effect volume; auth secrets excluded",
        }
        (output / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (output / "manifest.json").chmod(0o600)
        return {
            "backup": "complete",
            "image_id": image,
            "writers": "stopped",
            "files": list(result["files"]),
        }

    def restore(self, backup: Path) -> dict[str, Any]:
        manifest = json.loads((backup / "manifest.json").read_text())
        if manifest.get("schema_version") != 1 or set(manifest["files"]) != {
            "workflow.dump",
            "reports.tar",
        }:
            raise ValueError("Unsupported or incomplete backup")
        for name, expected in manifest["files"].items():
            if sha(backup / name) != expected:
                raise ValueError("Backup checksum mismatch")
        image = manifest["image_id"]
        if self.schema(image) != manifest["migrations"]:
            raise ValueError("Matching backup image/schema required")
        self.fresh()
        self.env["ARH_WORKFLOW_IMAGE"] = image
        self.compose("up", "-d", "workflow-db")
        self.wait_database()
        if self.postgres_version() // 10000 != manifest["postgres_version_num"] // 10000:
            raise ValueError("Restore requires the same PostgreSQL major version")
        with (backup / "workflow.dump").open("rb") as stream:
            self.compose(
                "exec",
                "-T",
                "workflow-db",
                "pg_restore",
                "-U",
                "arh",
                "-d",
                "arh_workflow",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                input_stream=stream,
            )
        with (backup / "reports.tar").open("rb") as stream:
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "python",
                "worker-a",
                "-m",
                "agent_reliability.workflow.snapshot",
                "restore",
                input_stream=stream,
            )
        if self.state() != manifest["migrations"]:
            raise ValueError("Restored migration records do not match the backup")
        # Workers stay stopped until the operator verifies the restored snapshot.
        return {
            "restore": "complete",
            "image_id": image,
            "writers": "stopped",
            "project": self.project,
        }

    def rollback(self, image: str) -> dict[str, Any]:
        # No automatic down migration. Reject incompatible images before stopping
        # or changing the currently running application.
        if self.schema(image) != self.state():
            raise ValueError(
                "Image/schema incompatible; restore a matching pre-upgrade snapshot into a fresh project"
            )
        self.env["ARH_WORKFLOW_IMAGE"] = image
        self.compose("stop", "api", "worker-a", "worker-b")
        self.compose("up", "-d", "migrate", "api", "worker-a", "worker-b")
        return {"rollback": "image-selected", "image_id": image, "readiness": "must be checked"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--image", help="Immutable image ID; never a mutable tag for rollback")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("validate")
    backup = sub.add_parser("backup")
    backup.add_argument("output", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("backup", type=Path)
    sub.add_parser("rollback")
    args = parser.parse_args()
    ops = Ops(args.project, image=args.image)
    if args.action == "validate":
        result = ops.validate()
    elif args.action == "backup":
        result = ops.backup(args.output)
    elif args.action == "restore":
        result = ops.restore(args.backup)
    else:
        if not args.image:
            parser.error("rollback requires --image sha256:...")
        result = ops.rollback(args.image)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

