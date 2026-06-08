from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.evals.cases import evaluation_case_catalog, list_evaluation_results, run_evaluation_cases


TEXT = {
    "zh": {
        "language": "语言",
        "title": "评估仪表盘",
        "subtitle": "浏览并运行真实 deterministic evaluation cases，覆盖 schema validity、tool success、reproducibility、report completeness 和 risk flag coverage。",
        "db": "DuckDB 路径",
        "catalog": "Evaluation Case Catalog",
        "select": "选择 case_id",
        "run": "运行选中用例",
        "results": "Persisted Results",
        "summary": "Summary",
        "error": "评估仪表盘无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Evaluation Dashboard",
        "subtitle": "Browse and run real deterministic evaluation cases for schema validity, tool success, reproducibility, report completeness, and risk flag coverage.",
        "db": "DuckDB path",
        "catalog": "Evaluation Case Catalog",
        "select": "Select case_id",
        "run": "Run selected cases",
        "results": "Persisted Results",
        "summary": "Summary",
        "error": "Evaluation Dashboard cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="evaluation_dashboard_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

catalog = evaluation_case_catalog()
st.subheader(text["catalog"])
st.dataframe(catalog, use_container_width=True, hide_index=True)
selected = st.multiselect(text["select"], catalog["case_id"].tolist(), default=catalog["case_id"].tolist()[:1])

if st.button(text["run"], disabled=not selected):
    try:
        results = run_evaluation_cases(db_path, case_ids=selected)
        st.json([result.__dict__ for result in results])
    except Exception as exc:
        st.error(f"{text['error']}: {exc}")

try:
    results_frame = list_evaluation_results(db_path)
    st.subheader(text["summary"])
    if not results_frame.empty:
        st.dataframe(results_frame.groupby(["category", "status"]).size().reset_index(name="count"), use_container_width=True, hide_index=True)
    st.subheader(text["results"])
    st.dataframe(results_frame, use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
