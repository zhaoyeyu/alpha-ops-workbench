from datetime import datetime, timedelta

import duckdb
import pytest

from alphaops.storage.duckdb import initialize_duckdb
from alphaops.synthetic.engine import (
    SyntheticIndexConfig,
    WeightingScheme,
    run_synthetic_index_from_storage,
    synthetic_universe_options,
)


def _insert_market_bars(db_path):
    base = datetime(2026, 1, 1)
    series = {
        "equity:a": ("A", "equity", [100.0, 110.0, 121.0], 1000.0),
        "equity:b": ("B", "equity", [100.0, 120.0, 132.0], 3000.0),
        "futures:mnq": ("MNQ", "futures", [100.0, 130.0, 143.0], 6000.0),
        "etf:qqq": ("QQQ", "etf", [100.0, 115.0, 126.5], 9000.0),
    }
    rows = []
    for instrument_id, (symbol, asset_class, prices, volume) in series.items():
        for offset, price in enumerate(prices):
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
                    volume,
                    "USD",
                    "CME" if asset_class == "futures" else "NASDAQ",
                    "synthetic_ui_fixture",
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


def test_synthetic_index_lab_runs_engine_from_stored_market_bars(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _insert_market_bars(db_path)

    options = synthetic_universe_options(db_path)
    result = run_synthetic_index_from_storage(
        db_path,
        config=SyntheticIndexConfig(
            index_id="synthetic_ui",
            name="Synthetic UI Test",
            weighting_scheme=WeightingScheme.LIQUIDITY_WEIGHT,
            max_weight=0.5,
            cost_bps=10,
            benchmark_id="etf:qqq",
        ),
        instrument_ids=["equity:a", "equity:b", "futures:mnq"],
    )

    assert set(options["asset_class"]) == {"equity", "etf", "futures"}
    assert not result.levels.empty
    assert result.levels["turnover"].iloc[0] == pytest.approx(1.0)
    assert not result.constituents.empty
    assert dict(zip(result.metrics["metric_name"], result.metrics["metric_value"], strict=True))["excess_return"] != 0
    assert result.methodology["asset_classes"] == ["equity", "futures"]
