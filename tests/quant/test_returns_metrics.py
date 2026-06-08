from datetime import datetime

import duckdb
import pandas as pd
import pytest

from alphaops.quant.metrics import compute_performance_metrics, drawdown_series, persist_metric_results
from alphaops.quant.returns import (
    compute_adjusted_returns,
    compute_benchmark_returns,
    persist_return_series,
)
from alphaops.storage.duckdb import initialize_duckdb


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "instrument_id": "eq:nvda",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 1),
                "frequency": "1d",
                "close": 100.0,
                "adj_close": 100.0,
                "source_id": "fixture_public",
            },
            {
                "instrument_id": "eq:nvda",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 2),
                "frequency": "1d",
                "close": 110.0,
                "adj_close": 110.0,
                "source_id": "fixture_public",
            },
            {
                "instrument_id": "eq:nvda",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 3),
                "frequency": "1d",
                "close": 104.5,
                "adj_close": 104.5,
                "source_id": "fixture_public",
            },
            {
                "instrument_id": "fut:mnq_cont",
                "asset_class": "futures",
                "timestamp": datetime(2026, 1, 1),
                "frequency": "1d",
                "close": 20000.0,
                "adj_close": 20000.0,
                "source_id": "fixture_private",
            },
            {
                "instrument_id": "fut:mnq_cont",
                "asset_class": "futures",
                "timestamp": datetime(2026, 1, 2),
                "frequency": "1d",
                "close": 20200.0,
                "adj_close": 20200.0,
                "source_id": "fixture_private",
            },
        ]
    )


def test_adjusted_returns_and_benchmark_are_deterministic() -> None:
    returns = compute_adjusted_returns(_bars(), run_id="run_returns_fixture")
    nvda = returns[returns["instrument_id"] == "eq:nvda"].sort_values("timestamp")
    benchmark = compute_benchmark_returns(returns, "eq:nvda")

    assert len(returns) == 3
    assert nvda["return_value"].tolist() == pytest.approx([0.10, -0.05])
    assert nvda["cumulative_return"].tolist() == pytest.approx([0.10, 0.045])
    assert benchmark["instrument_id"].unique().tolist() == ["eq:nvda"]


def test_performance_metrics_and_drawdown_are_deterministic() -> None:
    returns = compute_adjusted_returns(_bars(), run_id="run_metrics_fixture")
    nvda = returns[returns["instrument_id"] == "eq:nvda"]
    metrics = compute_performance_metrics(
        nvda,
        run_id="run_metrics_fixture",
        scope_id="eq:nvda",
        frequency="1d",
    )
    metric_map = dict(zip(metrics["metric_name"], metrics["metric_value"], strict=True))

    assert metric_map["cumulative_return"] == pytest.approx(0.045)
    assert metric_map["max_drawdown"] == pytest.approx(-0.05)
    assert metric_map["hit_rate"] == pytest.approx(0.5)
    assert metric_map["observation_count"] == 2.0
    assert drawdown_series(pd.Series([0.10, -0.05])).tolist() == pytest.approx([0.0, -0.05])


def test_returns_and_metrics_persist_to_duckdb(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    returns = compute_adjusted_returns(_bars(), run_id="run_persist_fixture")
    metrics = compute_performance_metrics(
        returns[returns["instrument_id"] == "eq:nvda"],
        run_id="run_persist_fixture",
        scope_id="eq:nvda",
        frequency="1d",
    )

    return_count = persist_return_series(db_path, returns)
    metric_count = persist_metric_results(db_path, metrics)

    with duckdb.connect(str(db_path)) as conn:
        persisted_returns = conn.execute("SELECT COUNT(*) FROM return_series").fetchone()[0]
        persisted_metrics = conn.execute("SELECT COUNT(*) FROM metric_results").fetchone()[0]

    assert return_count == 3
    assert metric_count == 6
    assert persisted_returns == 3
    assert persisted_metrics == 6
