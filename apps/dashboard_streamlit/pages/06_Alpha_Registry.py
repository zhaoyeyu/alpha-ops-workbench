from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState


TEXT = {
    "zh": {
        "language": "语言",
        "title": "Alpha 注册表",
        "subtitle": "查看真实持久化 Alpha Card、生命周期事件、指标快照、风险标记和报告链接，并执行可审计状态转换。",
        "db": "DuckDB 路径",
        "cards": "Alpha Cards",
        "state": "状态",
        "all": "全部",
        "query": "搜索 alpha_id / formula",
        "detail": "Alpha Detail",
        "select": "alpha_id",
        "metrics": "Metric History",
        "risks": "Risk Flags",
        "events": "Lifecycle Events",
        "reports": "Reports",
        "transition": "状态转换",
        "target": "目标状态",
        "actor": "actor",
        "reason": "reason",
        "report": "report_link",
        "run": "执行转换",
        "updated": "已转换到 {state}",
        "error": "Alpha 注册表无法加载",
    },
    "en": {
        "language": "Language",
        "title": "Alpha Registry",
        "subtitle": "Inspect persisted Alpha Cards, lifecycle events, metric snapshots, risk flags, report links, and run auditable state transitions.",
        "db": "DuckDB path",
        "cards": "Alpha Cards",
        "state": "State",
        "all": "All",
        "query": "Search alpha_id / formula",
        "detail": "Alpha Detail",
        "select": "alpha_id",
        "metrics": "Metric History",
        "risks": "Risk Flags",
        "events": "Lifecycle Events",
        "reports": "Reports",
        "transition": "State Transition",
        "target": "Target State",
        "actor": "actor",
        "reason": "reason",
        "report": "report_link",
        "run": "Run transition",
        "updated": "Transitioned to {state}",
        "error": "Alpha Registry cannot load",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="alpha_registry_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))
registry = AlphaRegistry(db_path)

try:
    filters = st.columns([1, 2])
    state_value = filters[0].selectbox(text["state"], [text["all"]] + [item.value for item in LifecycleState])
    query = filters[1].text_input(text["query"], value="")
    cards = registry.cards_frame(state=None if state_value == text["all"] else LifecycleState(state_value), query=query or None)
    st.subheader(text["cards"])
    st.dataframe(cards, use_container_width=True, hide_index=True)

    alpha_options = cards["alpha_id"].tolist() if not cards.empty else []
    selected = st.selectbox(text["select"], alpha_options, index=0 if alpha_options else None)
    if selected:
        card = registry.get_card(selected)
        st.subheader(text["detail"])
        st.json(
            {
                "alpha_id": card.alpha_id,
                "formula": card.formula,
                "lifecycle_state": card.lifecycle_state.value,
                "created_at": str(card.created_at),
                "report_links": card.report_links,
            }
        )
        cols = st.columns(3)
        with cols[0]:
            st.subheader(text["metrics"])
            st.dataframe(registry.metric_history(selected), use_container_width=True, hide_index=True)
        with cols[1]:
            st.subheader(text["risks"])
            st.dataframe(registry.risk_flags_frame(selected), use_container_width=True, hide_index=True)
        with cols[2]:
            st.subheader(text["reports"])
            st.dataframe(registry.reports_frame(selected), use_container_width=True, hide_index=True)

        st.subheader(text["events"])
        st.dataframe(registry.events_frame(selected), use_container_width=True, hide_index=True)

        with st.expander(text["transition"]):
            target = st.selectbox(text["target"], [item.value for item in LifecycleState])
            actor = st.text_input(text["actor"], value="reviewer")
            reason = st.text_input(text["reason"], value="manual_review")
            report_link = st.text_input(text["report"], value="")
            if st.button(text["run"]):
                updated = registry.transition(
                    selected,
                    LifecycleState(target),
                    actor=actor,
                    reason=reason,
                    report_link=report_link or None,
                )
                st.success(text["updated"].format(state=updated.lifecycle_state.value))
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
