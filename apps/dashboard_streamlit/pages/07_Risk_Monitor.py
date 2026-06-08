from __future__ import annotations

from datetime import datetime

import streamlit as st

from alphaops.config import load_config
from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState
from alphaops.risk.critic import RiskThresholds, run_risk_review_from_storage


TEXT = {
    "zh": {
        "language": "语言",
        "title": "风险监控",
        "subtitle": "基于真实 backtest、market_bars、quality reports 和 alpha lifecycle 运行风险评审，并写入 Alpha Registry 风险标记。",
        "db": "DuckDB 路径",
        "run_id": "backtest run_id",
        "alpha_id": "alpha_id",
        "thresholds": "风险阈值",
        "drawdown": "max_drawdown",
        "turnover": "max_average_turnover",
        "weight": "max_weight",
        "quality": "min_quality_score",
        "cost": "max_cost_ratio",
        "stale": "max_stale_days",
        "review": "运行风险评审",
        "summary": "Review Summary",
        "findings": "Risk Findings",
        "flags": "Persisted Risk Flags",
        "error": "风险监控无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Risk Monitor",
        "subtitle": "Run risk reviews from real backtests, market_bars, quality reports, and lifecycle state, then persist risk flags into Alpha Registry.",
        "db": "DuckDB path",
        "run_id": "backtest run_id",
        "alpha_id": "alpha_id",
        "thresholds": "Risk Thresholds",
        "drawdown": "max_drawdown",
        "turnover": "max_average_turnover",
        "weight": "max_weight",
        "quality": "min_quality_score",
        "cost": "max_cost_ratio",
        "stale": "max_stale_days",
        "review": "Run risk review",
        "summary": "Review Summary",
        "findings": "Risk Findings",
        "flags": "Persisted Risk Flags",
        "error": "Risk Monitor cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="risk_monitor_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))
run_id = st.text_input(text["run_id"], value="")
alpha_id = st.text_input(text["alpha_id"], value="")

st.subheader(text["thresholds"])
cols = st.columns(6)
max_drawdown = cols[0].number_input(text["drawdown"], min_value=0.0, value=0.2)
max_turnover = cols[1].number_input(text["turnover"], min_value=0.0, value=1.5)
max_weight = cols[2].number_input(text["weight"], min_value=0.0, max_value=1.0, value=0.4)
min_quality = cols[3].number_input(text["quality"], min_value=0.0, max_value=1.0, value=0.8)
max_cost = cols[4].number_input(text["cost"], min_value=0.0, value=0.02)
max_stale = cols[5].number_input(text["stale"], min_value=0, value=5)

if st.button(text["review"], disabled=not run_id):
    try:
        payload = run_risk_review_from_storage(
            db_path,
            run_id=run_id,
            alpha_id=alpha_id or None,
            thresholds=RiskThresholds(
                max_drawdown=float(max_drawdown),
                max_average_turnover=float(max_turnover),
                max_weight=float(max_weight),
                min_quality_score=float(min_quality),
                max_cost_ratio=float(max_cost),
                max_stale_days=int(max_stale),
            ),
            target_state=LifecycleState.ACTIVE,
            as_of=datetime.now(),
            persist_flags=True,
        )
        review = payload["review"]
        st.subheader(text["summary"])
        st.json(review.summary())
        st.subheader(text["findings"])
        st.dataframe([finding.__dict__ for finding in review.findings], use_container_width=True, hide_index=True)
        st.subheader(text["flags"])
        st.dataframe(AlphaRegistry(db_path).risk_flags_frame(review.alpha_id), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"{text['error']}: {exc}")
