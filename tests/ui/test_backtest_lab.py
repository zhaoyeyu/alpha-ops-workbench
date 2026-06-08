from datetime import datetime, timedelta

import duckdb

from alphaops.data.contracts import AssetClass, BacktestContract
from alphaops.quant.backtest import load_backtest_market_bars, run_backtest_from_storage
from alphaops.storage.duckdb import initialize_duckdb


def _insert_market_bars(db_path):
    base = datetime(2026, 1, 1)
    prices = {
        "equity:a": ("A", "equity", [100.0, 102.0, 101.0]),
        "equity:b": ("B", "equity", [100.0, 105.0, 110.0]),
        "futures:mnq": ("MNQ", "futures", [100.0, 110.0, 121.0]),
    }
    rows = []
    for instrument_id, (symbol, asset_class, series) in prices.items():
        for offset, price in enumerate(series):
            rows.append(
                (
                    instrument_id,
                    symbol,
                    asset_class,
                    base + timedelta(days=offset),
                    "1d",
                    price,
                    price,
                    price,
                    price,
                    price,
                    1000 + offset,
                    "USD",
                    "CME" if asset_class == "futures" else "NASDAQ",
                    "backtest_lab_fixture",
                    "fixture",
                    base,
                    "mnq_202603" if asset_class == "futures" else None,
                )
            )
    with duckdb.connect(str(db_path)) as conn:
        conn.executemany(
            "INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _contract() -> BacktestContract:
    return BacktestContract(
        contract_id="bt_ui_contract",
        asset_classes=[AssetClass.EQUITY, AssetClass.FUTURES],
        rebalance_frequency="1d",
        benchmark_id="equity:b",
        portfolio_constraints={
            "max_positions": 2,
            "max_weight_per_instrument": 0.3,
            "max_gross_exposure": 0.6,
            "long_short": False,
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


def test_backtest_lab_runs_and_persists_from_storage(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _insert_market_bars(db_path)

    bars = load_backtest_market_bars(
        db_path,
        asset_classes=[AssetClass.EQUITY, AssetClass.FUTURES],
        source_id="backtest_lab_fixture",
    )
    payload = run_backtest_from_storage(
        db_path,
        formula="rank(close)",
        contract=_contract(),
        run_id="bt_ui_run",
        source_id="backtest_lab_fixture",
        initial_capital=100_000,
    )
    result = payload["result"]

    with duckdb.connect(str(db_path)) as conn:
        run = conn.execute("SELECT alpha_id, final_equity FROM backtest_runs WHERE run_id = 'bt_ui_run'").fetchone()
        trades = conn.execute("SELECT COUNT(*) FROM backtest_trades WHERE run_id = 'bt_ui_run'").fetchone()[0]

    assert len(bars) == 9
    assert not result.equity_curve.empty
    assert result.trades["cost"].sum() > 0
    assert payload["inserted"] > 0
    assert run[0] == "bt_ui_run"
    assert run[1] > 100_000
    assert trades == len(result.trades)
