import json
import shutil
from pathlib import Path

import pytest
from conftest import ROOT

from agent_reliability.reporting.public_demo import build, public_payload, safe_json
from agent_reliability.tracing.recording import RecordingMismatch, load_trace, save_trace


def test_public_export_omits_provider_requests_gold_and_live_measurements(tmp_path):
    payload = public_payload(ROOT)
    assert len(payload["cases"]) == 4
    serialized = json.dumps(payload)
    assert '"request"' not in serialized and '"gold_sql"' not in serialized
    assert all(case["origin"] == "synthetic" for case in payload["cases"])
    result = build(ROOT, tmp_path)
    html = result.read_text()
    assert "__DEMO_DATA__" not in html and "__SCRIPT_HASH__" not in html
    assert "Content-Security-Policy" in html
    assert "innerHTML" not in html
    assert payload["reviewed_tasks"] == 0


def copy_export_inputs(destination: Path) -> None:
    for directory in ("tasks", "demo", "reports"):
        shutil.copytree(ROOT / directory, destination / directory)


def test_public_export_fails_closed_on_live_or_tampered_trace(tmp_path):
    copy_export_inputs(tmp_path)
    path = tmp_path / "demo/traces/q001.json"
    original = load_trace(path)
    save_trace(path, original.model_copy(update={"origin": "live"}))
    with pytest.raises(ValueError, match="synthetic"):
        public_payload(tmp_path)
    envelope = json.loads(path.read_text())
    envelope["trace"]["origin"] = "synthetic"
    path.write_text(json.dumps(envelope))
    with pytest.raises(RecordingMismatch):
        public_payload(tmp_path)


def test_script_closing_and_html_payload_are_inert_json():
    hostile = {"cell": '</script><img src=x onerror="alert(1)">&\u2028'}
    encoded = safe_json(hostile)
    assert "<" not in encoded and ">" not in encoded and "&" not in encoded
    assert json.loads(encoded) == hostile


def test_export_reports_incomplete_verification_without_inventing_test_count(tmp_path):
    copy_export_inputs(tmp_path)
    evidence = tmp_path / "reports/release-evidence.json"
    record = json.loads(evidence.read_text())
    record["commands"] = []
    record["all_checks_passed"] = False
    evidence.write_text(json.dumps(record))
    payload = public_payload(tmp_path)
    assert payload["verification"]["test_counts"] is None
    assert payload["verification"]["all_checks_passed"] is False
