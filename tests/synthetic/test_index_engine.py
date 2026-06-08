from datetime import datetime

import pandas as pd
import pytest

from alphaops.synthetic.engine import SyntheticIndexConfig, WeightingScheme, build_synthetic_index


def _bars() -> pd.DataFrame:
    rows = []
    prices = {
        "eq:a": [100.0, 110.0, 121.0],
        "eq:b": [100.0, 120.0, 132.0],
        "fut:mnq": [100.0, 130.0, 143.0],
        "etf:qqq": [100.0, 115.0, 126.5],
    }
    volumes = {"eq:a": 100.0, "eq:b": 300.0, "fut:mnq": 600.0, "etf:qqq": 1000.0}
    for instrument_id, series in prices.items():
        for day, price in enumerate(series, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "asset_class": "futures" if instrument_id.startswith("fut") else "equity",
                    "timestamp": datetime(2026, 1, day),
                    "close": price,
                    "adj_close": price,
                    "volume": volumes[instrument_id],
                }
            )
    return pd.DataFrame(rows)


def _factors() -> pd.DataFrame:
    rows = []
    for day in [1, 2]:
        for instrument_id, factor in {"eq:a": 1.0, "eq:b": 2.0, "fut:mnq": 3.0}.items():
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "timestamp": datetime(2026, 1, day),
                    "factor_value": factor,
                }
            )
    return pd.DataFrame(rows)


def test_liquidity_weighted_index_levels_and_constituents_are_reproducible() -> None:
    config = SyntheticIndexConfig(
        index_id="ai_infra_liquidity",
        name="AI Infrastructure Liquidity Index",
        weighting_scheme=WeightingScheme.LIQUIDITY_WEIGHT,
        max_weight=0.5,
        cost_bps=10.0,
        benchmark_id="etf:qqq",
    )

    result = build_synthetic_index(config, _bars())
    day_one_weights = result.constituents[result.constituents["timestamp"] == pd.Timestamp("2026-01-01")]
    weights = dict(zip(day_one_weights["instrument_id"], day_one_weights["weight"], strict=True))

    assert weights == pytest.approx({"eq:a": 0.125, "eq:b": 0.375, "fut:mnq": 0.5})
    assert result.levels["level"].iloc[0] == pytest.approx(1236.5)
    assert result.levels["turnover"].iloc[0] == pytest.approx(1.0)
    assert result.methodology["asset_classes"] == ["equity", "futures"]
    assert result.methodology["rebalance_count"] == 2


def test_benchmark_comparison_metrics_are_real_series() -> None:
    config = SyntheticIndexConfig(
        index_id="ai_infra_equal",
        name="AI Infrastructure Equal Index",
        weighting_scheme=WeightingScheme.EQUAL_WEIGHT,
        benchmark_id="etf:qqq",
    )

    result = build_synthetic_index(config, _bars())
    metrics = dict(zip(result.metrics["metric_name"], result.metrics["metric_value"], strict=True))

    assert result.benchmark["benchmark_level"].iloc[0] == pytest.approx(1150.0)
    assert "benchmark_cumulative_return" in metrics
    assert "excess_return" in metrics
    assert metrics["index_cumulative_return"] > 0


def test_factor_tilt_requires_and_uses_factor_values() -> None:
    config = SyntheticIndexConfig(
        index_id="ai_infra_factor_tilt",
        name="AI Infrastructure Factor Tilt Index",
        weighting_scheme=WeightingScheme.FACTOR_TILT,
        max_weight=0.6,
    )

    with pytest.raises(ValueError):
        build_synthetic_index(config, _bars())

    result = build_synthetic_index(config, _bars(), factor_values=_factors())
    day_one = result.constituents[result.constituents["timestamp"] == pd.Timestamp("2026-01-01")]
    weights = dict(zip(day_one["instrument_id"], day_one["weight"], strict=True))

    assert weights["fut:mnq"] > weights["eq:b"] > weights["eq:a"]
    assert result.methodology["weighting_scheme"] == "factor_tilt"
