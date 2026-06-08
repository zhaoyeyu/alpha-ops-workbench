from __future__ import annotations

from pathlib import Path

import streamlit as st

from alphaops.config import load_config
from alphaops.data.contracts import AssetClass
from alphaops.data.hub import (
    adapter_inventory,
    ingest_demo_market_data,
    ingest_private_file,
    ingest_public_equity_alpaca,
    ingest_public_equity_yfinance,
    ingest_public_market_massive,
    lineage_summary,
    sample_market_bars,
    storage_summary,
)


TEXT = {
    "zh": {
        "language": "语言",
        "title": "数据中心",
        "subtitle": "统一管理公开行情、本地私有文件和后续数据库数据源；所有数据进入同一套 Data Contract、Lineage、Quality 流程。",
        "db": "DuckDB 路径",
        "inventory": "数据源适配器",
        "public": "公开美股数据接入",
        "alpaca": "Alpaca 美股行情接入",
        "alpaca_help": "需要设置 ALPACA_API_KEY_ID 和 ALPACA_API_SECRET_KEY。IEX feed 通常适合免费/基础行情；SIP 取决于你的订阅权限。",
        "massive_help": "Massive 需要设置 MASSIVE_API_KEY。当前接入股票/ETF 聚合行情，数据会进入同一套 Data Contract、Lineage、Quality 流程。",
        "provider": "数据源",
        "feed": "feed",
        "massive_asset_class": "Massive 资产类型",
        "private_path": "私有 CSV/Parquet 文件路径",
        "private_upload": "上传私有 CSV/Parquet 文件",
        "private_ingestion": "本地私有数据接入",
        "demo": "体验流程用样本数据",
        "demo_help": "样本数据仅用于熟悉界面和流程，不可用于研究结论。",
        "asset_class": "资产类型",
        "symbols": "标的代码",
        "start": "开始日期",
        "end": "结束日期",
        "frequency": "频率",
        "fetch": "拉取公开美股数据",
        "fetch_alpaca": "拉取 Alpaca 行情",
        "fetch_massive": "拉取 Massive 行情",
        "ingest": "导入私有文件",
        "load_demo": "写入样本数据",
        "storage": "存储覆盖",
        "lineage": "Lineage",
        "sample": "标准化行情样本",
        "missing_file": "请先填写或上传真实 CSV/Parquet 文件。",
        "loaded": "已写入 {rows} 行，lineage_id={lineage_id}",
        "demo_loaded": "已写入 {rows} 行样本数据，source_id={source_id}",
        "error": "数据中心无法加载当前存储状态",
    },
    "en": {
        "language": "Language",
        "title": "Data Hub",
        "subtitle": "Manage public market data, private local files, and future database sources through one Data Contract, Lineage, and Quality flow.",
        "db": "DuckDB path",
        "inventory": "Adapter Inventory",
        "public": "Public US Equity Ingestion",
        "alpaca": "Alpaca US Equity Market Data",
        "alpaca_help": "Requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY. IEX is usually suitable for basic/free access; SIP depends on your subscription.",
        "massive_help": "Massive requires MASSIVE_API_KEY. Current integration loads stock/ETF aggregate bars into the same Data Contract, Lineage, and Quality flow.",
        "provider": "Provider",
        "feed": "feed",
        "massive_asset_class": "Massive Asset Class",
        "private_path": "Private CSV/Parquet path",
        "private_upload": "Upload private CSV/Parquet file",
        "private_ingestion": "Private Data Ingestion Adapter",
        "demo": "Sample Data For Workflow Trial",
        "demo_help": "Sample data is for learning the workflow only, not for research conclusions.",
        "asset_class": "Asset Class",
        "symbols": "Symbols",
        "start": "Start",
        "end": "End",
        "frequency": "Frequency",
        "fetch": "Fetch public equity data",
        "fetch_alpaca": "Fetch Alpaca bars",
        "fetch_massive": "Fetch Massive bars",
        "ingest": "Ingest private file",
        "load_demo": "Write sample data",
        "storage": "Storage Coverage",
        "lineage": "Lineage",
        "sample": "Standardized Market Bar Sample",
        "missing_file": "Enter or upload a real CSV/Parquet file first.",
        "loaded": "Wrote {rows} rows, lineage_id={lineage_id}",
        "demo_loaded": "Wrote {rows} sample rows, source_id={source_id}",
        "error": "Data Hub cannot load current storage state",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="data_hub_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

st.subheader(text["inventory"])
private_path = st.text_input(text["private_path"], value="")
st.dataframe(adapter_inventory(private_path or None), use_container_width=True, hide_index=True)

st.subheader(text["public"])
provider = st.radio(text["provider"], ["massive", "yfinance", "alpaca"], horizontal=True)
public_cols = st.columns([1.4, 1, 1, 0.8])
public_symbols = public_cols[0].text_input(text["symbols"], value="NVDA,MSFT")
public_start = public_cols[1].text_input(text["start"], value="2025-01-01", key="public_start")
public_end = public_cols[2].text_input(text["end"], value="2026-01-01", key="public_end")
public_frequency = public_cols[3].selectbox(text["frequency"], ["1d", "1wk", "1mo"], index=0, key="public_frequency")
alpaca_feed = st.selectbox(text["feed"], ["iex", "sip", "delayed_sip", "otc"], index=0) if provider == "alpaca" else "iex"
massive_asset_class = AssetClass.EQUITY
if provider == "alpaca":
    st.caption(text["alpaca_help"])
elif provider == "massive":
    massive_asset_class = AssetClass(
        st.selectbox(text["massive_asset_class"], [AssetClass.EQUITY.value, AssetClass.ETF.value], index=0)
    )
    st.caption(text["massive_help"])

button_label = text["fetch_alpaca"] if provider == "alpaca" else text["fetch_massive"] if provider == "massive" else text["fetch"]
if st.button(button_label):
    try:
        symbols_payload = [item.strip() for item in public_symbols.split(",") if item.strip()]
        if provider == "alpaca":
            result = ingest_public_equity_alpaca(
                db_path=db_path,
                symbols=symbols_payload,
                start=public_start,
                end=public_end,
                frequency=public_frequency,
                feed=alpaca_feed,
            )
        elif provider == "massive":
            result = ingest_public_market_massive(
                db_path=db_path,
                symbols=symbols_payload,
                start=public_start,
                end=public_end,
                frequency=public_frequency,
                asset_class=massive_asset_class,
            )
        else:
            result = ingest_public_equity_yfinance(
                db_path=db_path,
                symbols=symbols_payload,
                start=public_start,
                end=public_end,
                frequency=public_frequency,
            )
        st.success(text["loaded"].format(rows=result["rows"], lineage_id=result["lineage_id"]))
        st.dataframe(result["sample"], use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"{text['error']}: {exc}")

st.subheader(text["private_ingestion"])
uploaded_file = st.file_uploader(text["private_upload"], type=["csv", "parquet", "pq"])
if uploaded_file is not None:
    upload_dir = Path(config.paths.storage_dir) / "raw" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    uploaded_path = upload_dir / uploaded_file.name
    uploaded_path.write_bytes(uploaded_file.getbuffer())
    private_path = str(uploaded_path)
    st.caption(private_path)

cols = st.columns([1.1, 1.4, 1, 1, 0.8])
asset_class = cols[0].selectbox(text["asset_class"], [item.value for item in AssetClass], index=0)
symbols = cols[1].text_input(text["symbols"], value="", key="private_symbols")
start = cols[2].text_input(text["start"], value="2025-01-01", key="private_start")
end = cols[3].text_input(text["end"], value="2026-12-31", key="private_end")
frequency = cols[4].selectbox(text["frequency"], ["1d", "1h", "1m"], index=0, key="private_frequency")

if st.button(text["ingest"], disabled=not private_path):
    if not private_path:
        st.warning(text["missing_file"])
    else:
        try:
            result = ingest_private_file(
                db_path=db_path,
                file_path=Path(private_path),
                asset_class=AssetClass(asset_class),
                instruments=[item.strip() for item in symbols.split(",") if item.strip()],
                start=start,
                end=end,
                frequency=frequency,
            )
            st.success(text["loaded"].format(rows=result["rows"], lineage_id=result["lineage_id"]))
            st.dataframe(result["sample"], use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"{text['error']}: {exc}")

st.subheader(text["demo"])
st.caption(text["demo_help"])
if st.button(text["load_demo"]):
    result = ingest_demo_market_data(db_path)
    st.success(text["demo_loaded"].format(rows=result["rows"], source_id=result["source_id"]))
    st.dataframe(result["sample"], use_container_width=True, hide_index=True)

st.subheader(text["storage"])
try:
    summary = storage_summary(db_path)
    metrics = st.columns(4)
    metrics[0].metric("rows", summary["rows"])
    metrics[1].metric("instruments", summary["instruments"])
    metrics[2].metric("asset_classes", len(summary["coverage"]))
    metrics[3].metric("latest_timestamp", summary["latest_timestamp"] or "n/a")
    st.dataframe(
        [{"asset_class": key, "rows": value} for key, value in summary["coverage"].items()],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader(text["lineage"])
    st.dataframe(lineage_summary(db_path), use_container_width=True, hide_index=True)

    st.subheader(text["sample"])
    st.dataframe(sample_market_bars(db_path), use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"{text['error']}: {exc}")
