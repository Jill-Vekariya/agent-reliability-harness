"""Snapshot, trace and configuration boundaries without Docker or PostgreSQL."""

import io
import json
import logging
import sqlite3
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_reliability.workflow.api import create_app
from agent_reliability.workflow.auth import DemoAuth, Principal
from agent_reliability.workflow.snapshot import create, restore
from agent_reliability.workflow.telemetry import Telemetry, carrier
from scripts.verify_workflow_deployment import Verification
from scripts.workflow_ops import Ops

TOKEN = "deployment-test-token-00000000000"
AUTH = DemoAuth({TOKEN: Principal("tenant-a", "operator")})
ROOT = Path(__file__).resolve().parents[2]


def test_snapshot_restores_sqlite_and_refuses_existing_target(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with sqlite3.connect(source / "effects.sqlite") as conn:
        conn.execute("CREATE TABLE effects(id text primary key)")
        conn.execute("INSERT INTO effects VALUES('synthetic-once')")
    (source / "trace.json").write_text('{"fixture":true}')
    stream = io.BytesIO()
    create(source, stream)
    target = tmp_path / "target"
    target.mkdir()
    restore(target, io.BytesIO(stream.getvalue()))
    with sqlite3.connect(target / "effects.sqlite") as conn:
        assert conn.execute("SELECT id FROM effects").fetchall() == [("synthetic-once",)]
    assert (target / "trace.json").read_bytes() == (source / "trace.json").read_bytes()
    with pytest.raises(ValueError, match="fresh empty"):
        restore(target, io.BytesIO(stream.getvalue()))


@pytest.mark.parametrize(
    "name,kind",
    [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)],
)
def test_untrusted_archive_cannot_escape_or_link(tmp_path, name, kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        archive.addfile(member)
    with pytest.raises(ValueError, match="Unsafe"):
        restore(tmp_path, io.BytesIO(stream.getvalue()))
    assert list(tmp_path.iterdir()) == []


def test_spans_propagate_context_and_never_log_unknown_fields(caplog):
    caplog.set_level(logging.INFO)
    telemetry = Telemetry()
    secret = "deployment-secret-that-must-not-be-exported"
    with telemetry.span("workflow.http", request_id="a" * 32, password=secret):
        trace, parent = carrier()
    with telemetry.span(
        "workflow.attempt",
        trace_id=trace,
        parent_span_id=parent,
        job_id="job-fixture",
        raw_prompt=secret,
    ):
        assert carrier()[0] == trace
    telemetry.close()
    rows = [json.loads(r.message) for r in caplog.records if r.message.startswith('{"')]
    spans = [r for r in rows if r.get("event") == "workflow_span"]
    assert len(spans) == 2 and spans[1]["parent_span_id"] == spans[0]["span_id"]
    assert secret not in caplog.text


def test_metrics_authentication_and_principal_scope():
    class MetricsStore:
        def metrics(self, tenant):
            assert tenant == "tenant-a"
            return {
                "jobs": {"succeeded": 2},
                "attempts": {},
                "operations": {},
                "queue_age_seconds": 0,
                "stale_result_rejections": 0,
                "budget": None,
            }

    with TestClient(create_app(ROOT, MetricsStore(), AUTH)) as client:
        assert client.get("/metrics").status_code == 401
        response = client.get(
            "/metrics", headers={"Authorization": "Bearer " + TOKEN, "X-Tenant-ID": "tenant-b"}
        )
        assert response.status_code == 200
        assert 'arh_workflow_jobs{state="succeeded"} 2' in response.text
        assert "tenant-a" not in response.text and "tenant-b" not in response.text
        assert response.headers["X-Request-ID"] != response.headers["X-Trace-ID"]


def test_incompatible_rollback_refused_before_container_mutation(monkeypatch):
    # No credentials or Docker needed: exercise the preflight rejection ordering.
    ops = object.__new__(Ops)
    monkeypatch.setattr(ops, "schema", lambda image: {"002": "old"})
    monkeypatch.setattr(ops, "state", lambda: {"003": "new"})
    monkeypatch.setattr(
        ops, "compose", lambda *a, **kw: pytest.fail("mutated before compatibility check")
    )
    with pytest.raises(ValueError, match="incompatible"):
        ops.rollback("sha256:" + "a" * 64)


def test_existing_project_refusal_never_tears_down_foreign_resources(tmp_path, monkeypatch):
    verification = Verification("arh-existing", 8093, tmp_path / "evidence")

    class ForeignProject:
        def fresh(self):
            raise ValueError("existing resources")

    verification.ops = ForeignProject()
    monkeypatch.setattr(
        verification, "record", lambda *a, **kw: pytest.fail("touched foreign project")
    )
    with pytest.raises(ValueError, match="existing"):
        verification.build()
    verification.down()
    assert verification.owned_projects == set()


def image_receipt_fixture(tmp_path, monkeypatch):
    import hashlib
    import sys

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    source = checkout / "source.py"
    source.write_text("# source used by the recorded build\n")
    monkeypatch.setattr(sys.modules[Verification.__module__], "ROOT", checkout)
    verification = Verification("arh-receipt", 8093, tmp_path / "evidence")
    verification.metadata = tmp_path / "images.json"
    metadata = {
        "project": verification.project,
        "image_id": "sha256:" + "a" * 64,
        "checks_image_id": "sha256:" + "b" * 64,
        "source_digest": "source-digest",
        "source_hashes": {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()},
    }
    verification.metadata.write_text(json.dumps(metadata))

    class RecordedImages:
        def __init__(self):
            self.env = {}
            self.inspections = []

        def inspect(self, image):
            self.inspections.append(image)
            return {"Config": {"Labels": {"io.arh.workflow.source_digest": "source-digest"}}}

    verification.ops = RecordedImages()
    return verification, metadata, source


def test_continuation_pins_application_and_checks_to_recorded_immutable_images(
    tmp_path, monkeypatch
):
    verification, metadata, _ = image_receipt_fixture(tmp_path, monkeypatch)
    assert verification.selected_image() == metadata["image_id"]
    assert verification.ops.inspections == [metadata["image_id"], metadata["checks_image_id"]]
    assert verification.ops.env["ARH_WORKFLOW_IMAGE"] == metadata["image_id"]
    assert verification.ops.env["ARH_WORKFLOW_CHECKS_IMAGE"] == metadata["checks_image_id"]


def test_continuation_refuses_unmatched_checks_image_before_claiming_resources(
    tmp_path, monkeypatch
):
    verification, metadata, _ = image_receipt_fixture(tmp_path, monkeypatch)
    original = verification.ops.inspect

    def inspect(image):
        if image == metadata["checks_image_id"]:
            return {"Config": {"Labels": {"io.arh.workflow.source_digest": "foreign-source"}}}
        return original(image)

    monkeypatch.setattr(verification.ops, "inspect", inspect)
    with pytest.raises(ValueError, match="recorded source digest"):
        verification.selected_image()
    assert verification.owned_projects == set()


def test_changed_source_requires_rebuild_before_any_image_or_resource_operation(
    tmp_path, monkeypatch
):
    verification, _, source = image_receipt_fixture(tmp_path, monkeypatch)
    source.write_text("# changed after the recorded build\n")
    with pytest.raises(ValueError, match="Source changed"):
        verification.selected_image()
    assert verification.ops.inspections == []
    assert verification.owned_projects == set()


def test_old_receipt_without_checks_image_cannot_resume_tests(tmp_path, monkeypatch):
    verification, metadata, _ = image_receipt_fixture(tmp_path, monkeypatch)
    metadata.pop("checks_image_id")
    verification.metadata.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="Checks image receipt is missing"):
        verification.selected_image()
    assert verification.ops.inspections == []


@pytest.mark.parametrize("fixture", ["data/manifest.json", "reports/releases/example.json"])
def test_build_binds_copied_fixture_bytes_and_refuses_changed_checkout(
    tmp_path, monkeypatch, fixture
):
    import sys

    module = sys.modules[Verification.__module__]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in (
        "pyproject.toml",
        "uv.lock",
        "Dockerfile.workflow",
        "compose.workflow.yaml",
        ".python-version",
        ".dockerignore",
        ".gitattributes",
        "scripts/workflow_init.sql",
    ):
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    data = checkout / fixture
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_bytes(b'{"fixture": true}\r\n')
    monkeypatch.setattr(module, "ROOT", checkout)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "fixture-revision\n")
    verification = Verification("arh-inputs", 8093, tmp_path / "evidence")
    inspections = []

    class Images:
        def fresh(self):
            pass

        def image(self):
            return "sha256:" + "a" * 64

        def inspect(self, image):
            inspections.append(image)
            return {
                "Id": "sha256:" + "b" * 64,
                "Config": {
                    "Labels": {
                        "io.arh.workflow.source_digest": verification.env[
                            "ARH_WORKFLOW_SOURCE_DIGEST"
                        ]
                    }
                },
            }

    verification.ops = Images()
    monkeypatch.setattr(verification, "compose", lambda *a, **kw: b"")
    verification.build()
    metadata = json.loads(verification.metadata.read_text())
    assert fixture in metadata["source_hashes"]
    # Repairing CRLF to the trusted LF blob must still force a new image build.
    data.write_bytes(b'{"fixture": true}\n')
    inspections.clear()
    verification.owned_projects.clear()
    with pytest.raises(ValueError, match="Source changed"):
        verification.selected_image()
    assert inspections == [] and verification.owned_projects == set()
