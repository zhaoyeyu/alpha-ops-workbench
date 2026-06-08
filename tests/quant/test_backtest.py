from datetime import datetime

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass, BacktestContract
from alphaops.quant.backtest import run_backtest
from alphaops.storage.duckdb import initialize_duckdb


def _bars() -> pd.DataFrame:
    rows = []
    prices = {
        "eq:a": [100.0, 102.0, 101.0],
        "eq:b": [100.0, 105.0, 110.0],
        "fut:mnq": [100.0, 110.0, 121.0],
    }
    for instrument_id, series in prices.items():
        for day, price in enumerate(series, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "asset_class": "futures" if instrument_id.startswith("fut") else "equity",
                    "timestamp": datetime(2026, 1, day),
                    "close": price,
                    "adj_close": price,
                }
            )
    return pd.DataFrame(rows)


def _factors() -> pd.DataFrame:
    rows = []
    factor_by_day = {
        1: {"eq:a": 1.0, "eq:b": 2.0, "fut:mnq": 3.0},
        2: {"eq:a": 1.0, "eq:b": 3.0, "fut:mnq": 2.0},
    }
    for day, values in factor_by_day.items():
        for instrument_id, factor in values.items():
            rows.append(
                {
                    "alpha_id": "alpha_backtest_fixture",
                    "instrument_id": instrument_id,
                    "timestamp": datetime(2026, 1, day),
                    "factor_value": factor,
                }
            )
    return pd.DataFrame(rows)


def _contract() -> BacktestContract:
    return BacktestContract(
        contract_id="bt_multi_asset_fixture",
        asset_classes=[AssetClass.EQUITY, AssetClass.FUTURES],
        rebalance_frequency="1d",
        benchmark_id="eq:b",
        portfolio_constraints={
            "max_positions": 2,
            "max_weight_per_instrument": 0.3,
            "max_gross_exposure": 0.6,
            "long_short": False,
        },
        equity_cost_model={"commission_bps": 1.0, "slippage_bps": 1.0, "min_commission": 0.0},
        futures_cost_model={
            "commission_per_contract": 1.5,
            "slippage_ticks": 1.0,
            "exchange_fee_per_contract": 0.5,
        },
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


def test_backtest_outputs_real_weights_trades_equity_and_metrics() -> None:
    result = run_backtest(
        _contract(),
        _factors(),
        _bars(),
        run_id="run_backtest_fixture",
        initial_capital=100_000,
    )

    assert result.alpha_id == "alpha_backtest_fixture"
    assert set(result.weights["instrument_id"]) >= {"eq:b", "fut:mnq"}
    assert result.trades["cost"].sum() > 0
    assert result.trades[result.trades["asset_class"] == "futures"]["contract_count"].notna().any()
    assert result.trades[result.trades["asset_class"] == "futures"]["margin_requirement"].notna().any()
    assert result.equity_curve["equity"].iloc[-1] > 100_000
    assert set(result.metrics["metric_name"]) == {
        "cumulative_return",
        "max_drawdown",
        "average_turnover",
        "total_cost",
        "period_count",
        "mean_period_return",
    }


def test_backtest_persists_run_storage(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    result = run_backtest(
        _contract(),
        _factors(),
        _bars(),
        run_id="run_backtest_persist",
        initial_capital=100_000,
    )

    inserted = result.persist(db_path)

    with duckdb.connect(str(db_path)) as conn:
        run = conn.execute(
            "SELECT alpha_id, final_equity FROM backtest_runs WHERE run_id = ?",
            ["run_backtest_persist"],
        ).fetchone()
        trade_count = conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]
        metric_count = conn.execute(
            "SELECT COUNT(*) FROM metric_results WHERE run_id = ?",
            ["run_backtest_persist"],
        ).fetchone()[0]

    assert inserted > 0
    assert run[0] == "alpha_backtest_fixture"
    assert run[1] > 100_000
    assert trade_count == len(result.trades)
    assert metric_count == 6
