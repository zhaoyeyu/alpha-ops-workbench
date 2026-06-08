from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.synthetic.engine import (
    SyntheticIndexConfig,
    WeightingScheme,
    run_synthetic_index_from_storage,
    synthetic_universe_options,
)


TEXT = {
    "zh": {
        "language": "语言",
        "title": "合成指数实验室",
        "subtitle": "用已入库行情定义篮子、权重方法、调仓频率、benchmark 和成本假设，并生成指数水平、成分权重、换手和方法论。",
        "db": "DuckDB 路径",
        "universe": "可选标的",
        "config": "指数配置",
        "index_id": "index_id",
        "name": "指数名称",
        "base": "base_level",
        "rebalance": "rebalance_frequency",
        "scheme": "weighting_scheme",
        "max_weight": "max_weight",
        "cost": "cost_bps",
        "benchmark": "benchmark_id",
        "constituents": "成分 instrument_id",
        "start": "开始",
        "end": "结束",
        "run": "生成指数",
        "levels": "指数水平",
        "weights": "成分权重",
        "metrics": "Benchmark / 成本指标",
        "methodology": "方法论",
        "error": "合成指数实验室无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Synthetic Index Lab",
        "subtitle": "Build a basket from stored market data, choose weighting, rebalance, benchmark, and cost assumptions, then generate real levels, weights, turnover, and methodology.",
        "db": "DuckDB path",
        "universe": "Available Instruments",
        "config": "Index Config",
        "index_id": "index_id",
        "name": "Index Name",
        "base": "base_level",
        "rebalance": "rebalance_frequency",
        "scheme": "weighting_scheme",
        "max_weight": "max_weight",
        "cost": "cost_bps",
        "benchmark": "benchmark_id",
        "constituents": "Constituent instrument_id",
        "start": "Start",
        "end": "End",
        "run": "Generate index",
        "levels": "Index Levels",
        "weights": "Constituent Weights",
        "metrics": "Benchmark / Cost Metrics",
        "methodology": "Methodology",
        "error": "Synthetic Index Lab cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="synthetic_index_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

try:
    universe = synthetic_universe_options(db_path)
    st.subheader(text["universe"])
    st.dataframe(universe, use_container_width=True, hide_index=True)

    st.subheader(text["config"])
    instrument_options = universe["instrument_id"].tolist() if not universe.empty else []
    cols = st.columns([1, 1, 1, 1, 1, 1])
    index_id = cols[0].text_input(text["index_id"], value="synthetic_short_alpha")
    name = cols[1].text_input(text["name"], value="Synthetic Short Alpha")
    base_level = cols[2].number_input(text["base"], min_value=1.0, value=1000.0)
    rebalance_frequency = cols[3].text_input(text["rebalance"], value="1d")
    weighting_scheme = cols[4].selectbox(text["scheme"], [item.value for item in WeightingScheme])
    cost_bps = cols[5].number_input(text["cost"], min_value=0.0, value=5.0)

    selected = st.multiselect(text["constituents"], instrument_options, default=instrument_options[: min(3, len(instrument_options))])
    benchmark_id = st.selectbox(text["benchmark"], [""] + instrument_options, index=0)
    range_cols = st.columns(3)
    start = range_cols[0].text_input(text["start"], value="")
    end = range_cols[1].text_input(text["end"], value="")
    max_weight = range_cols[2].number_input(text["max_weight"], min_value=0.01, max_value=1.0, value=0.4)

    if st.button(text["run"], disabled=not selected):
        result = run_synthetic_index_from_storage(
            db_path,
            config=SyntheticIndexConfig(
                index_id=index_id,
                name=name,
                base_level=base_level,
                rebalance_frequency=rebalance_frequency,
                weighting_scheme=WeightingScheme(weighting_scheme),
                max_weight=max_weight,
                cost_bps=cost_bps,
                benchmark_id=benchmark_id or None,
            ),
            instrument_ids=selected,
            start=start or None,
            end=end or None,
        )
        st.subheader(text["levels"])
        st.dataframe(result.levels, use_container_width=True, hide_index=True)
        if not result.levels.empty:
            st.line_chart(result.levels.set_index("timestamp")[["level"]])
        st.subheader(text["weights"])
        st.dataframe(result.constituents, use_container_width=True, hide_index=True)
        st.subheader(text["metrics"])
        st.dataframe(result.metrics, use_container_width=True, hide_index=True)
        st.subheader(text["methodology"])
        st.json(result.methodology)
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
