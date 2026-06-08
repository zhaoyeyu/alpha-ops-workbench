from __future__ import annotations

import json

import streamlit as st

from alphaops.agents.orchestrator import agent_trace_frame, get_agent_run_state, list_agent_runs, run_workflow_from_dict
from alphaops.config import load_config


TEXT = {
    "zh": {
        "language": "语言",
        "title": "Agent 控制台",
        "subtitle": "运行和审计真实 orchestrator workflow，查看工具调用、重试、错误、审批等待、风险阻断和持久化运行状态。",
        "db": "DuckDB 路径",
        "run": "运行 Workflow",
        "run_id": "run_id",
        "plan": "WorkflowPlan JSON",
        "approvals": "Approvals JSON",
        "execute": "执行",
        "runs": "Agent Runs",
        "trace": "Tool Trace",
        "state": "Run State",
        "error": "Agent 控制台无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Agent Console",
        "subtitle": "Run and audit real orchestrator workflows with tool calls, retries, errors, approvals, risk blocks, and persisted run state.",
        "db": "DuckDB path",
        "run": "Run Workflow",
        "run_id": "run_id",
        "plan": "WorkflowPlan JSON",
        "approvals": "Approvals JSON",
        "execute": "Execute",
        "runs": "Agent Runs",
        "trace": "Tool Trace",
        "state": "Run State",
        "error": "Agent Console cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="agent_console_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

with st.expander(text["run"], expanded=True):
    run_id = st.text_input(text["run_id"], value="agent_console_run")
    plan_json = st.text_area(
        text["plan"],
        value=json.dumps(
            {
                "workflow_name": "data_quality_review",
                "steps": [{"step_id": "quality", "tool_name": "data_quality.profile_market_bars", "payload": {"rows": []}}],
            },
            indent=2,
        ),
        height=180,
    )
    approvals_json = st.text_area(text["approvals"], value="{}", height=80)
    if st.button(text["execute"]):
        try:
            state = run_workflow_from_dict(
                db_path,
                run_id=run_id,
                plan_payload=json.loads(plan_json),
                approvals=json.loads(approvals_json),
            )
            st.json(json.loads(state.as_json()))
        except Exception as exc:
            st.error(f"{text['error']}: {exc}")

try:
    runs = list_agent_runs(db_path)
    st.subheader(text["runs"])
    st.dataframe(runs, use_container_width=True, hide_index=True)
    run_options = runs["run_id"].tolist() if not runs.empty else []
    selected = st.selectbox(text["run_id"], run_options, index=0 if run_options else None)
    if selected:
        st.subheader(text["trace"])
        st.dataframe(agent_trace_frame(db_path, selected), use_container_width=True, hide_index=True)
        st.subheader(text["state"])
        st.json(get_agent_run_state(db_path, selected))
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
