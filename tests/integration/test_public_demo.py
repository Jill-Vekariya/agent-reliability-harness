import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT

from agent_reliability.reporting.public_demo import build, public_payload, safe_json
from agent_reliability.tracing.recording import RecordingMismatch, load_trace, save_trace
from agent_reliability.util import file_hash


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
    assert payload["verification"]["test_counts"]["passed"] > 64
    assert payload["verification"]["release"].startswith("v")


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


def test_public_export_preserves_unicode_and_csp_under_non_utf8_locale(tmp_path):
    copy_export_inputs(tmp_path)
    shutil.copytree(ROOT / "web", tmp_path / "web")
    # Include non-ASCII task text as well as the template's typography. Alter a
    # disposable input only; the published tasks and recordings stay untouched.
    tasks_path = tmp_path / "tasks/normal/candidates.yaml"
    original = tasks_path.read_text(encoding="utf-8")
    tasks_path.write_text(original + "\n# Unicode task metadata: café 中文\n", encoding="utf-8")
    output = tmp_path / "site"
    script = (
        "import sys; from pathlib import Path; "
        "from agent_reliability.reporting.public_demo import build; "
        "build(Path(sys.argv[1]), Path(sys.argv[2]))"
    )
    environment = dict(
        os.environ,
        LC_ALL="C",
        LANG="C",
        PYTHONCOERCECLOCALE="0",
        PYTHONUTF8="0",
    )
    subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", script, str(tmp_path), str(output)],
        env=environment,
        check=True,
        capture_output=True,
        timeout=30,
    )
    raw = (output / "index.html").read_bytes()
    html = raw.decode("utf-8")
    assert "inspect the boundary" in html and "View source ↗" in html
    assert b"\r\n" not in raw
    assert "__DEMO_DATA__" not in html
    for tag, directive in (("style", "style-src"), ("script", "script-src")):
        match = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.S)
        assert match is not None
        digest = base64.b64encode(hashlib.sha256(match.group(1).encode("utf-8")).digest()).decode()
        assert f"{directive} 'sha256-{digest}'" in html


def test_export_reports_incomplete_verification_without_inventing_test_count(tmp_path):
    copy_export_inputs(tmp_path)
    index_path = tmp_path / "reports/public-evidence.json"
    index = json.loads(index_path.read_text())
    evidence = tmp_path / "reports" / index["source"]
    record = json.loads(evidence.read_text())
    record["published_image_tests"] = {}
    evidence.write_text(json.dumps(record))
    index["sha256"] = file_hash(evidence)
    index_path.write_text(json.dumps(index))
    payload = public_payload(tmp_path)
    assert payload["verification"]["test_counts"] is None
    assert payload["verification"]["all_checks_passed"] is False


@pytest.mark.parametrize("fault", ["escaped_path", "changed_hash"])
def test_public_release_evidence_rejects_invalid_reference(tmp_path, fault):
    copy_export_inputs(tmp_path)
    path = tmp_path / "reports/public-evidence.json"
    record = json.loads(path.read_text())
    record["source" if fault == "escaped_path" else "sha256"] = (
        "../outside.json" if fault == "escaped_path" else "0" * 64
    )
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="evidence"):
        public_payload(tmp_path)


def test_public_release_count_cannot_be_boolean(tmp_path):
    copy_export_inputs(tmp_path)
    path = tmp_path / "reports/public-evidence.json"
    index = json.loads(path.read_text())
    source = tmp_path / "reports" / index["source"]
    record = json.loads(source.read_text())
    record["published_image_tests"]["passed"] = True
    source.write_text(json.dumps(record))
    index["sha256"] = file_hash(source)
    path.write_text(json.dumps(index))
    assert public_payload(tmp_path)["verification"]["test_counts"] is None
