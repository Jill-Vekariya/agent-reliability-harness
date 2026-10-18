"""Fault-inject a trusted worker process; never expose worker selection to the agent."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_reliability.models import Limits
from agent_reliability.sandbox import Sandbox


def substitute_worker(monkeypatch, tmp_path, body, *, small_pipe=False):
    worker = tmp_path / "worker_fault.py"
    worker.write_text(body)
    actual = subprocess.Popen
    launched = {}

    def start(command, **kwargs):
        process = actual([*command[:-1], str(worker)], **kwargs)
        launched.update(pid=process.pid, cwd=Path(kwargs["cwd"]))
        if small_pipe:
            import fcntl

            fcntl.fcntl(process.stdin.fileno(), fcntl.F_SETPIPE_SZ, 4096)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    return launched


def assert_reaped(launched):
    with pytest.raises(ProcessLookupError):
        os.kill(launched["pid"], 0)
    assert not launched["cwd"].exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux pipe-capacity fault injection")
def test_deadline_includes_blocked_input_pipe(sandbox, tmp_path, monkeypatch):
    launched = substitute_worker(
        monkeypatch,
        tmp_path,
        "import time\ntime.sleep(60)\n",
        small_pipe=True,
    )
    limited = Sandbox(sandbox.database, Limits(wall_seconds=0.05, max_sql_bytes=65536))
    start = time.monotonic()
    result = limited.run("SELECT '" + "x" * 32000 + "'")
    assert not result.ok and result.resource_limited
    assert time.monotonic() - start < 2
    assert_reaped(launched)


def test_stdout_flood_is_bounded_and_worker_reaped(sandbox, tmp_path, monkeypatch):
    launched = substitute_worker(
        monkeypatch,
        tmp_path,
        "import os\nwhile True: os.write(1,b'x'*4096)\n",
    )
    result = Sandbox(sandbox.database, Limits(max_output_bytes=2048)).run("SELECT 1")
    assert not result.ok and result.resource_limited and result.error == "Worker output limit"
    assert_reaped(launched)


def test_child_that_closes_stdout_but_ignores_terminate_is_killed(sandbox, tmp_path, monkeypatch):
    launched = substitute_worker(
        monkeypatch,
        tmp_path,
        "import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nos.close(1)\ntime.sleep(60)\n",
    )
    result = Sandbox(sandbox.database, Limits(wall_seconds=0.1)).run("SELECT 1")
    assert not result.ok and result.resource_limited
    assert_reaped(launched)


@pytest.mark.parametrize("output", ["not JSON", '{"ok":"yes"}', ""])
def test_malformed_or_empty_worker_reply_fails_closed(sandbox, tmp_path, monkeypatch, output):
    launched = substitute_worker(monkeypatch, tmp_path, "print(" + repr(output) + ")\n")
    result = sandbox.run("SELECT 1")
    assert not result.ok and result.error_kind == "worker"
    assert_reaped(launched)


def test_unpaired_unicode_is_an_argument_failure(sandbox):
    result = sandbox.run("SELECT '\ud800'")
    assert not result.ok and result.error_kind == "arguments"


def test_parent_interruption_still_reaps_worker_and_removes_private_directory(
    sandbox, tmp_path, monkeypatch
):
    import selectors

    launched = substitute_worker(monkeypatch, tmp_path, "import time\ntime.sleep(60)\n")

    def interrupt(*args):
        raise KeyboardInterrupt("Synthetic parent interruption")

    monkeypatch.setattr(selectors.DefaultSelector, "select", interrupt)
    with pytest.raises(KeyboardInterrupt):
        sandbox.run("SELECT 1")
    assert_reaped(launched)
