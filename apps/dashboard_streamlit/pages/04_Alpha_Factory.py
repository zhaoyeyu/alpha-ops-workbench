from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.data.contracts import AssetClass
from alphaops.lifecycle.factory import create_alpha_candidate_from_storage


TEXT = {
    "zh": {
        "language": "语言",
        "title": "Alpha 工厂",
        "subtitle": "输入 Alpha DSL 公式，基于真实 market_bars 计算 factor preview、IC/RankIC 分数，并提交到 Alpha Registry 的 registry_review 状态。",
        "db": "DuckDB 路径",
        "formula": "Alpha DSL formula",
        "asset": "资产类型",
        "all": "全部",
        "symbol": "标的",
        "source": "source_id",
        "start": "开始",
        "end": "结束",
        "horizon": "horizon",
        "register": "提交 registry_review",
        "run": "创建候选",
        "candidate": "候选 Alpha",
        "preview": "Factor Preview",
        "metrics": "IC / RankIC Metrics",
        "payload": "Registry Review Payload",
        "card": "Registry Card",
        "error": "Alpha 工厂无法创建候选",
    },
    "en": {
        "language": "Language",
        "title": "Alpha Factory",
        "subtitle": "Enter an Alpha DSL formula, calculate factor preview and IC/RankIC scores from real market_bars, and submit it to Alpha Registry review.",
        "db": "DuckDB path",
        "formula": "Alpha DSL formula",
        "asset": "Asset Class",
        "all": "All",
        "symbol": "Symbol",
        "source": "source_id",
        "start": "Start",
        "end": "End",
        "horizon": "horizon",
        "register": "Submit registry_review",
        "run": "Create candidate",
        "candidate": "Candidate",
        "preview": "Factor Preview",
        "metrics": "IC / RankIC Metrics",
        "payload": "Registry Review Payload",
        "card": "Registry Card",
        "error": "Alpha Factory cannot create candidate",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="alpha_factory_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

formula = st.text_area(text["formula"], value="rank(close)", height=80)
cols = st.columns([1, 1, 1, 1, 1, 1])
asset = cols[0].selectbox(text["asset"], [text["all"]] + [item.value for item in AssetClass])
symbol = cols[1].text_input(text["symbol"], value="")
source_id = cols[2].text_input(text["source"], value="")
start = cols[3].text_input(text["start"], value="")
end = cols[4].text_input(text["end"], value="")
horizon = cols[5].number_input(text["horizon"], min_value=1, value=1)
register = st.checkbox(text["register"], value=True)

if st.button(text["run"]):
    try:
        result = create_alpha_candidate_from_storage(
            db_path,
            formula=formula,
            asset_class=None if asset == text["all"] else AssetClass(asset),
            symbol=symbol or None,
            source_id=source_id or None,
            start=start or None,
            end=end or None,
            horizon=int(horizon),
            register_for_review=register,
        )
        candidate = result["candidate"]
        card = result["card"]
        st.subheader(text["candidate"])
        st.json(
            {
                "candidate_id": candidate.candidate_id,
                "state": candidate.state,
                "score": candidate.score,
                "dependencies": candidate.dependencies,
                "operator_names": candidate.operator_names,
                "duplicate_of": candidate.duplicate_of,
            }
        )
        st.subheader(text["preview"])
        st.dataframe(candidate.factor_preview, use_container_width=True, hide_index=True)
        st.subheader(text["metrics"])
        st.dataframe(candidate.evaluation.summary, use_container_width=True, hide_index=True)
        st.subheader(text["payload"])
        st.json(result["payload"])
        if card:
            st.subheader(text["card"])
            st.json({"alpha_id": card.alpha_id, "lifecycle_state": card.lifecycle_state.value, "metrics": card.metrics})
    except Exception as exc:
        st.error(f"{text['error']}: {exc}")
