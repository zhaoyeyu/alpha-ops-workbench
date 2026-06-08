from __future__ import annotations

import streamlit as st

from alphaops.config import load_config
from alphaops.data.contracts import AssetClass, BacktestContract
from alphaops.quant.backtest import run_backtest_from_storage


TEXT = {
    "zh": {
        "language": "语言",
        "title": "回测实验室",
        "subtitle": "从真实 market_bars 和 Alpha DSL 公式运行研究级回测，支持资产类型、调仓、成本模型、组合约束、期货交易规则和持久化输出。",
        "db": "DuckDB 路径",
        "formula": "Alpha DSL formula",
        "contract": "Backtest Contract",
        "run_id": "run_id",
        "contract_id": "contract_id",
        "assets": "资产类型",
        "rebalance": "rebalance_frequency",
        "benchmark": "benchmark_id",
        "source": "source_id",
        "capital": "initial_capital",
        "max_positions": "max_positions",
        "max_weight": "max_weight_per_instrument",
        "gross": "max_gross_exposure",
        "long_short": "long_short",
        "run": "运行回测",
        "curve": "Equity / Drawdown",
        "metrics": "Metrics",
        "trades": "Trades",
        "weights": "Weights",
        "error": "回测实验室无法运行",
    },
    "en": {
        "language": "Language",
        "title": "Backtest Lab",
        "subtitle": "Run research-grade backtests from real market_bars and Alpha DSL formulas with asset classes, rebalance, costs, constraints, futures rules, and persisted outputs.",
        "db": "DuckDB path",
        "formula": "Alpha DSL formula",
        "contract": "Backtest Contract",
        "run_id": "run_id",
        "contract_id": "contract_id",
        "assets": "Asset Classes",
        "rebalance": "rebalance_frequency",
        "benchmark": "benchmark_id",
        "source": "source_id",
        "capital": "initial_capital",
        "max_positions": "max_positions",
        "max_weight": "max_weight_per_instrument",
        "gross": "max_gross_exposure",
        "long_short": "long_short",
        "run": "Run backtest",
        "curve": "Equity / Drawdown",
        "metrics": "Metrics",
        "trades": "Trades",
        "weights": "Weights",
        "error": "Backtest Lab cannot run",
    },
}


language = st.sidebar.radio(
    TEXT["zh"]["language"],
    ["zh", "en"],
    index=0,
    format_func=lambda item: "中文" if item == "zh" else "English",
    key="backtest_lab_language",
)
text = TEXT[language]

st.title(text["title"])
st.caption(text["subtitle"])

config = load_config()
db_path = st.sidebar.text_input(text["db"], value=str(config.paths.duckdb_path))

formula = st.text_area(text["formula"], value="rank(close)", height=80)
st.subheader(text["contract"])
cols = st.columns([1, 1, 1, 1, 1])
run_id = cols[0].text_input(text["run_id"], value="bt_streamlit_run")
contract_id = cols[1].text_input(text["contract_id"], value="bt_streamlit_contract")
rebalance = cols[2].text_input(text["rebalance"], value="1d")
source_id = cols[3].text_input(text["source"], value="")
initial_capital = cols[4].number_input(text["capital"], min_value=1.0, value=1_000_000.0)

asset_classes = st.multiselect(text["assets"], [item.value for item in AssetClass], default=[AssetClass.EQUITY.value])
benchmark_id = st.text_input(text["benchmark"], value="")
constraint_cols = st.columns(4)
max_positions = constraint_cols[0].number_input(text["max_positions"], min_value=1, value=5)
max_weight = constraint_cols[1].number_input(text["max_weight"], min_value=0.01, max_value=1.0, value=0.3)
gross = constraint_cols[2].number_input(text["gross"], min_value=0.01, value=0.6)
long_short = constraint_cols[3].checkbox(text["long_short"], value=False)

if st.button(text["run"], disabled=not asset_classes):
    try:
        contract = BacktestContract(
            contract_id=contract_id,
            asset_classes=[AssetClass(item) for item in asset_classes],
            rebalance_frequency=rebalance,
            benchmark_id=benchmark_id or None,
            portfolio_constraints={
                "max_positions": int(max_positions),
                "max_weight_per_instrument": float(max_weight),
                "max_gross_exposure": float(gross),
                "long_short": bool(long_short),
            },
            equity_cost_model={"commission_bps": 1.0, "slippage_bps": 1.0, "min_commission": 0.0},
            futures_cost_model={"commission_per_contract": 1.5, "slippage_ticks": 1.0, "exchange_fee_per_contract": 0.5},
            futures_rules={
                "contract_multiplier": 2.0,
                "margin": 1200.0,
                "leverage": 5.0,
                "continuous_contract": "MNQ.C",
                "roll_logic": "volume_open_interest",
                "position_direction": "long",
                "trading_sessions": ["CME_GLOBEX_DAY", "CME_GLOBEX_NIGHT"],
                "tick_size": 0.25,
                "night_session": True,
            },
        )
        payload = run_backtest_from_storage(
            db_path,
            formula=formula,
            contract=contract,
            run_id=run_id,
            source_id=source_id or None,
            initial_capital=float(initial_capital),
        )
        result = payload["result"]
        st.subheader(text["curve"])
        st.dataframe(result.equity_curve, use_container_width=True, hide_index=True)
        st.line_chart(result.equity_curve.set_index("timestamp")[["equity", "drawdown"]])
        st.subheader(text["metrics"])
        st.dataframe(result.metrics, use_container_width=True, hide_index=True)
        st.subheader(text["trades"])
        st.dataframe(result.trades, use_container_width=True, hide_index=True)
        st.subheader(text["weights"])
        st.dataframe(result.weights, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"{text['error']}: {exc}")
