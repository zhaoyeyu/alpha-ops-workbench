from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from alphaops.config import load_config
from alphaops.reports.renderer import list_report_inventory, read_report_preview, render_report, save_report_document


TEXT = {
    "zh": {
        "language": "语言",
        "title": "报告中心",
        "subtitle": "用 report renderer 从真实产品产物生成可复现 Markdown/HTML 报告，并登记到 DuckDB reports 表。",
        "db": "DuckDB 路径",
        "output": "输出目录",
        "generate": "生成报告",
        "report_id": "report_id",
        "title_input": "标题",
        "type": "report_type",
        "source": "source_run_id",
        "sections": "sections JSON",
        "links": "source_links JSON",
        "run": "生成并登记",
        "inventory": "Report Inventory",
        "preview": "Preview",
        "saved": "已保存 {path}",
        "error": "报告中心无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Report Center",
        "subtitle": "Generate reproducible Markdown/HTML reports from real product artifacts with the report renderer and register them in DuckDB reports.",
        "db": "DuckDB path",
        "output": "Output directory",
        "generate": "Generate Report",
        "report_id": "report_id",
        "title_input": "Title",
        "type": "report_type",
        "source": "source_run_id",
        "sections": "sections JSON",
        "links": "source_links JSON",
        "run": "Generate and register",
        "inventory": "Report Inventory",
        "preview": "Preview",
        "saved": "Saved {path}",
        "error": "Report Center cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="report_center_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))
output_dir = st.sidebar.text_input(text["output"], value=str(Path(config.paths.storage_dir) / "reports"))

with st.expander(text["generate"], expanded=True):
    cols = st.columns(4)
    report_id = cols[0].text_input(text["report_id"], value="report_manual")
    report_title = cols[1].text_input(text["title_input"], value="AlphaOps Report")
    report_type = cols[2].text_input(text["type"], value="manual")
    source_run_id = cols[3].text_input(text["source"], value="manual")
    sections_json = st.text_area(text["sections"], value=json.dumps({"Summary": {"status": "generated"}}, indent=2), height=120)
    links_json = st.text_area(text["links"], value=json.dumps(["alphaops:manual"], indent=2), height=80)
    if st.button(text["run"]):
        try:
            document = render_report(
                report_id=report_id,
                title=report_title,
                sections=json.loads(sections_json),
                source_links=json.loads(links_json),
                reproducibility={"renderer": "alphaops.reports.renderer", "report_type": report_type},
            )
            paths = save_report_document(db_path, document, output_dir=output_dir, report_type=report_type, source_run_id=source_run_id)
            st.success(text["saved"].format(path=paths["md"]))
        except Exception as exc:
            st.error(f"{text['error']}: {exc}")

try:
    inventory = list_report_inventory(db_path, require_existing=True)
    st.subheader(text["inventory"])
    st.dataframe(inventory, use_container_width=True, hide_index=True)
    options = inventory["path"].tolist() if not inventory.empty else []
    selected = st.selectbox(text["preview"], options, index=0 if options else None)
    if selected:
        st.markdown(read_report_preview(selected))
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
