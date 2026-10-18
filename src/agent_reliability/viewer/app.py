import json
import os
from pathlib import Path

import streamlit as st

from agent_reliability.cli import project_root
from agent_reliability.evaluation.tasks import load_tasks
from agent_reliability.models import Trace
from agent_reliability.runner import run_offline
from agent_reliability.tracing.recording import load_trace

st.set_page_config(page_title="Agent Reliability Lab", page_icon="🧪", layout="wide")
ROOT = project_root()


def show_trace(trace: Trace, *, compact: bool = False) -> None:
    left, middle, right = st.columns(3)
    left.metric("Execution", trace.mode.upper())
    middle.metric("Steps", sum(e.kind == "tool" for e in trace.events))
    right.metric(
        "Fixture API spend", "$0" if trace.origin == "synthetic" else trace.cost_usd or "Unknown"
    )
    st.caption(f"{trace.origin.upper()} • {trace.termination} • {trace.config}")
    if trace.final and trace.final.get("status") == "answered":
        st.success("Final answer is bound to a complete tool result.")
        import pandas as pd

        st.dataframe(
            pd.DataFrame(trace.final["rows"], columns=trace.final["columns"]),
            hide_index=True,
            width="stretch",
        )
    elif trace.final:
        st.info("Final status: " + str(trace.final["status"]))
    else:
        st.warning("No supported final answer. Inspect the failed step below.")
    events = [e for e in trace.events if not compact or e.kind == "tool"]
    for event in events:
        payload = event.payload
        label = f"{event.index + 1:02d} · {event.kind.upper()}"
        if event.kind == "tool":
            label += " · " + payload["name"]
            if payload["output"].get("blocked"):
                label += " · BLOCKED"
        with st.expander(label, expanded=event.kind == "tool"):
            if event.kind == "tool":
                if payload["arguments"].get("sql"):
                    st.code(payload["arguments"]["sql"], language="sql")
                else:
                    st.json(payload["arguments"])
                output = payload["output"]
                if output.get("error"):
                    st.error(output["error"])
                st.json(output, expanded=False)
            elif event.kind == "model":
                response = payload["response"]
                st.caption(
                    f"Tokens: input={response.get('input_tokens')} / output={response.get('output_tokens')} (unknown for synthetic fixtures)"
                )
                st.json(payload, expanded=False)
            else:
                st.json(payload)
            st.caption(
                f"Recorded local duration: {event.latency_ms:.2f} ms • not live-provider latency"
            )


st.caption("AGENT RELIABILITY HARNESS / ENGINEERING RELEASE 0.1")
st.title("Make agent behavior inspectable.")
st.markdown("Follow the SQL, inspect a failure, and check the boundary that stopped it.")
st.info(
    "Offline demo · Prewritten synthetic responses · No API key · Live model results not yet measured"
)
tasks = {t.id: t for t in load_tasks(ROOT)}
summary = st.session_state.get("summary") or json.loads((ROOT / "demo/summary.json").read_text())
trace_root = Path(st.session_state.get("trace_root", str(ROOT / "demo")))
a, b, c, d = st.columns(4)
a.metric("Candidate questions", len(tasks))
b.metric("Regression suite", "20 tasks")
c.metric("Human-reviewed tasks", "0")
d.metric("Paid API spend", "$0")
explore, compare, status = st.tabs(["Trace explorer", "Scripted recovery", "Study & checks"])

with explore:
    with st.sidebar:
        st.subheader("Filter traces")
        category = st.selectbox(
            "Category", ["All"] + sorted({r["category"] for r in summary["rows"]})
        )
        outcome = st.selectbox(
            "Outcome", ["All", "Expected behavior passed", "Needs investigation"]
        )
        failure = st.selectbox(
            "Failure category",
            ["All"]
            + sorted({r["failure_category"] for r in summary["rows"] if r["failure_category"]}),
        )
        config_filter = st.selectbox(
            "Configuration", ["All"] + sorted({r["config"] for r in summary["rows"]})
        )
        split_filter = st.selectbox(
            "Split", ["All"] + sorted({r["split"] for r in summary["rows"]})
        )
        st.caption(
            "All bundled questions are development candidates. No frozen test campaign exists yet."
        )
    rows = [
        r
        for r in summary["rows"]
        if (category == "All" or r["category"] == category)
        and (outcome == "All" or r["behavior_passed"] == (outcome == "Expected behavior passed"))
        and (failure == "All" or r["failure_category"] == failure)
        and (config_filter == "All" or r["config"] == config_filter)
        and (split_filter == "All" or r["split"] == split_filter)
    ]
    if not rows:
        st.warning("No traces match these filters.")
    else:
        selected = st.selectbox(
            "Choose a question",
            [r["task_id"] for r in rows],
            format_func=lambda x: f"{x} — {tasks[x].question}",
        )
        row = next(r for r in rows if r["task_id"] == selected)
        st.subheader(tasks[selected].question)
        st.caption(
            f"{tasks[selected].difficulty.title()} • {tasks[selected].category} • Review pending • {tasks[selected].family_id}"
        )
        trace = load_trace(trace_root / row["trace_path"])
        if tasks[selected].category == "injection":
            st.warning(
                "Injected text below is deliberately hostile test data. This is a synthetic attack walkthrough, not evidence of real-model resistance."
            )
            st.caption(
                "Attack text reached a later synthetic provider request: "
                + str(row.get("injection_exposed", False))
            )
        show_trace(trace)

with compare:
    st.subheader("One schema error, followed by a scripted recovery")
    st.caption(
        "Different prewritten response scripts are used. This explains the retry machinery; it does not estimate a model improvement or an engineering treatment effect."
    )
    first, second = st.columns(2)
    with first:
        st.markdown("**Baseline fixture: invented column**")
        show_trace(load_trace(ROOT / "demo/traces/q002.json"), compact=True)
    with second:
        st.markdown("**Recovery fixture: bounded retry**")
        show_trace(load_trace(ROOT / "demo/recovery.json"), compact=True)

with status:
    st.subheader("Evidence before claims")
    st.table(
        [
            {
                "Stage": "R0 · offline engineering",
                "State": "Implemented; see release evidence for executed checks",
            },
            {
                "Stage": "R1 · reviewed benchmark",
                "State": "Pending human review, 150-task corpus, 20 sourced Spider adaptations, grouped holdout",
            },
            {
                "Stage": "R2 · empirical study",
                "State": "Pending approved API budget and fresh model runs",
            },
            {"Stage": "Public deployment", "State": "Not published; localhost demo only"},
        ]
    )
    st.markdown(
        "**The headline campaign is planned at 2,100 attempts. No headline model attempt has been run.**"
    )
    st.caption(
        "Pass@1, pass@5, safety incident rates, Pareto tradeoffs, and classifier/human agreement remain not yet measured."
    )
    if st.button("Run the 20-task offline regression", type="primary"):
        with st.spinner("Executing current SQL tools and grader; no network/model calls…"):
            result = run_offline(
                ROOT,
                artifact_root=Path(os.environ.get("ARH_ARTIFACT_DIR", str(ROOT / "artifacts"))),
            )
        st.session_state["summary"] = result
        st.session_state["trace_root"] = result["run_dir"]
        if result["gate_passed"]:
            st.success(
                "Engineering regression gate passed. All 20 tasks executed against current tools."
            )
        else:
            st.error(
                "Regression gate failed; inspect incompatible traces and per-task regressions."
            )
        st.json({k: v for k, v in result.items() if k != "rows"}, expanded=False)
    with st.expander("Recorded release evidence"):
        evidence = ROOT / "reports/release-evidence.json"
        if evidence.exists():
            st.json(json.loads(evidence.read_text()), expanded=False)
        else:
            st.info("Release evidence is still being collected.")
