from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.data.contracts import AssetClass
from alphaops.data.quality import (
    profile_stored_market_bars,
    quality_issue_table,
    quality_overview,
    quality_score_history,
    symbol_quality_drilldown,
)


TEXT = {
    "zh": {
        "language": "语言",
        "title": "数据质量",
        "subtitle": "检查真实 market_bars 数据集的完整性、价格区间、跳变、重复、期货合约字段和覆盖缺口，并追踪到来源 lineage。",
        "db": "DuckDB 路径",
        "run": "运行质量画像",
        "asset_class": "资产类型",
        "all": "全部",
        "symbol": "标的",
        "source_id": "source_id",
        "start": "开始",
        "end": "结束",
        "dataset_id": "dataset_id",
        "profile": "生成质量报告",
        "created": "已生成质量报告 {report_id}，score={score}",
        "overview": "质量概览",
        "reports": "最近报告",
        "history": "分数历史",
        "issues": "Issue 明细",
        "severity": "严重性",
        "code": "Issue code",
        "drilldown": "标的 Drilldown",
        "instrument_id": "instrument_id",
        "error": "数据质量页面无法加载当前状态",
    },
    "en": {
        "language": "Language",
        "title": "Data Quality",
        "subtitle": "Profile real market_bars datasets for missing values, OHLC ranges, jumps, duplicates, futures contract fields, coverage gaps, and source lineage.",
        "db": "DuckDB path",
        "run": "Run Quality Profile",
        "asset_class": "Asset Class",
        "all": "All",
        "symbol": "Symbol",
        "source_id": "source_id",
        "start": "Start",
        "end": "End",
        "dataset_id": "dataset_id",
        "profile": "Generate quality report",
        "created": "Created quality report {report_id}, score={score}",
        "overview": "Quality Overview",
        "reports": "Recent Reports",
        "history": "Score History",
        "issues": "Issue Details",
        "severity": "Severity",
        "code": "Issue code",
        "drilldown": "Symbol Drilldown",
        "instrument_id": "instrument_id",
        "error": "Data Quality cannot load current state",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="data_quality_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

with st.expander(text["run"], expanded=True):
    cols = st.columns([1, 1, 1, 1, 1, 1.2])
    selected_asset = cols[0].selectbox(text["asset_class"], [text["all"]] + [item.value for item in AssetClass])
    symbol = cols[1].text_input(text["symbol"], value="")
    source_id = cols[2].text_input(text["source_id"], value="")
    start = cols[3].text_input(text["start"], value="")
    end = cols[4].text_input(text["end"], value="")
    dataset_id = cols[5].text_input(text["dataset_id"], value="")

    if st.button(text["profile"]):
        report = profile_stored_market_bars(
            db_path,
            asset_class=None if selected_asset == text["all"] else AssetClass(selected_asset),
            symbol=symbol or None,
            source_id=source_id or None,
            start=start or None,
            end=end or None,
            dataset_id=dataset_id or None,
        )
        st.success(text["created"].format(report_id=report.report_id, score=f"{report.quality_score:.3f}"))

try:
    overview = quality_overview(db_path)
    st.subheader(text["overview"])
    metrics = st.columns(4)
    metrics[0].metric("quality_reports", overview["report_count"])
    metrics[1].metric("quality_issues", overview["issue_count"])
    metrics[2].metric("average_score", f"{overview['average_score']:.3f}")
    metrics[3].metric("severity_types", len(overview["issues_by_severity"]))

    left, right = st.columns([1.5, 1])
    with left:
        st.subheader(text["reports"])
        st.dataframe(overview["recent_reports"], use_container_width=True, hide_index=True)
        st.subheader(text["history"])
        history = quality_score_history(db_path)
        st.dataframe(history, use_container_width=True, hide_index=True)
        if not history.empty:
            st.line_chart(history.set_index("created_at")[["quality_score"]])

    with right:
        st.subheader(text["issues"])
        severity = st.selectbox(text["severity"], [""] + ["error", "warning"], index=0)
        code = st.text_input(text["code"], value="")
        st.dataframe(
            quality_issue_table(db_path, severity=severity or None, code=code or None),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader(text["drilldown"])
        instrument_id = st.text_input(text["instrument_id"], value="")
        if instrument_id:
            drilldown = symbol_quality_drilldown(db_path, instrument_id)
            st.dataframe(drilldown["coverage"], use_container_width=True, hide_index=True)
            st.dataframe(drilldown["issues"], use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
