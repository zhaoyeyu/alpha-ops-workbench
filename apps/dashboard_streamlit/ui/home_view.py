from __future__ import annotations

import streamlit as st

from apps.dashboard_streamlit.ui.state import REQUIRED_PAGES, HomeStateError, collect_home_state


TEXT = {
    "zh": {
        "title": "AlphaOps Workbench",
        "subtitle": "本地量化研究工作台",
        "language": "语言",
        "coverage": "数据覆盖",
        "quality": "数据质量",
        "alpha": "Alpha 生命周期",
        "risk": "风险标记",
        "agent": "Agent 运行",
        "reports": "报告",
        "evals": "评估用例",
        "nav": "产品页面",
        "implemented": "已实现能力",
        "state_error": "无法加载系统状态",
        "ready": "市场数据已覆盖 Equity、ETF、Futures。",
        "missing": "当前还缺少这些资产类型的数据：{assets}。请到“数据中心”拉取公开美股数据，或导入本地 CSV/Parquet 私有数据。",
        "empty_alpha": "Alpha 注册表为空。接入市场数据后，可在“Alpha 工厂”创建候选 Alpha。",
        "empty_eval": "评估用例尚未运行。可在“评估仪表盘”执行内置用例。",
    },
    "en": {
        "title": "AlphaOps Workbench",
        "subtitle": "Local quantitative research workbench",
        "language": "Language",
        "coverage": "Data Coverage",
        "quality": "Data Quality",
        "alpha": "Alpha Lifecycle",
        "risk": "Risk Flags",
        "agent": "Agent Runs",
        "reports": "Reports",
        "evals": "Evaluation Cases",
        "nav": "Product Pages",
        "implemented": "Implemented Capabilities",
        "state_error": "Cannot load system state",
        "ready": "Market data covers Equity, ETF, and Futures.",
        "missing": "Missing market data for: {assets}. Use Data Hub to fetch public US equity data or ingest local CSV/Parquet private data.",
        "empty_alpha": "Alpha Registry is empty. Create candidates in Alpha Factory after ingesting market data.",
        "empty_eval": "Evaluation cases have not run yet. Use Evaluation Dashboard to run built-in cases.",
    },
}


def render_home() -> None:
    language = st.sidebar.radio(
        TEXT["zh"]["language"],
        ["zh", "en"],
        index=0,
        format_func=lambda item: "中文" if item == "zh" else "English",
        key="home_language",
    )
    text = TEXT[language]

    st.title(text["title"])
    st.caption(text["subtitle"])

    try:
        state = collect_home_state()
    except HomeStateError as exc:
        st.error(f"{text['state_error']}: {exc}")
        st.stop()

    missing = state["readiness"]["missing_market_coverage"]
    if missing:
        st.warning(text["missing"].format(assets=", ".join(missing)))
    else:
        st.success(text["ready"])
    if not state["readiness"]["alpha_registry_ready"]:
        st.info(text["empty_alpha"])
    if not state["readiness"]["evaluation_ready"]:
        st.info(text["empty_eval"])

    top = st.columns(4)
    top[0].metric("Equity", state["data_coverage"].get("equity", 0))
    top[1].metric("ETF", state["data_coverage"].get("etf", 0))
    top[2].metric("Futures", state["data_coverage"].get("futures", 0))
    top[3].metric(text["reports"], state["report_count"])

    left, right = st.columns([2, 1])
    with left:
        st.subheader(text["coverage"])
        st.dataframe(
            [{"asset_class": key, "rows": value} for key, value in state["data_coverage"].items()],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader(text["nav"])
        st.dataframe([{"page": page} for page in REQUIRED_PAGES], use_container_width=True, hide_index=True)

    with right:
        st.subheader(text["quality"])
        st.metric("quality_score", f"{state['quality']['average_score']:.3f}")
        st.metric("quality_reports", state["quality"]["report_count"])
        st.subheader(text["alpha"])
        st.json(state["alpha_states"])
        st.subheader(text["risk"])
        st.json(state["risk_flags"])
        st.subheader(text["agent"])
        st.json(state["agent_runs"])
        st.subheader(text["evals"])
        st.json(state["evaluation_cases"])

    st.subheader(text["implemented"])
    st.dataframe(state["implemented_capabilities"], use_container_width=True, hide_index=True)
