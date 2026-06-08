"""Synthetic index methodology, weighting, rebalance, and benchmark comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from alphaops.storage.duckdb import initialize_duckdb


class WeightingScheme(StrEnum):
    EQUAL_WEIGHT = "equal_weight"
    LIQUIDITY_WEIGHT = "liquidity_weight"
    FACTOR_TILT = "factor_tilt"


class SyntheticIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_id: str
    name: str
    base_level: float = Field(default=1000.0, gt=0)
    rebalance_frequency: str = "1d"
    weighting_scheme: WeightingScheme = WeightingScheme.EQUAL_WEIGHT
    max_weight: float = Field(default=0.4, gt=0, le=1)
    cost_bps: float = Field(default=0.0, ge=0)
    benchmark_id: str | None = None

    @field_validator("rebalance_frequency")
    @classmethod
    def validate_rebalance_frequency(cls, value: str) -> str:
        normalized = value.lower()
        if normalized in {"1d", "daily", "d"}:
            return "1d"
        if normalized.endswith("d") and normalized[:-1].isdigit() and int(normalized[:-1]) > 0:
            return normalized
        raise ValueError("rebalance_frequency must be daily or Nd")


@dataclass(frozen=True)
class SyntheticIndexResult:
    config: SyntheticIndexConfig
    levels: pd.DataFrame
    constituents: pd.DataFrame
    benchmark: pd.DataFrame
    metrics: pd.DataFrame
    methodology: dict[str, object]


def build_synthetic_index(
    config: SyntheticIndexConfig,
    market_bars: pd.DataFrame,
    *,
    factor_values: pd.DataFrame | None = None,
) -> SyntheticIndexResult:
    bars, price_column = _prepare_bars(market_bars)
    benchmark = _benchmark_series(config, bars, price_column)
    investable = bars.copy()
    if config.benchmark_id:
        investable = investable[investable["instrument_id"] != config.benchmark_id]
    if investable.empty:
        raise ValueError("no investable constituents available")

    returns = _forward_returns(investable, price_column)
    rebalance_dates = _rebalance_dates(sorted(returns["timestamp"].unique()), config.rebalance_frequency)
    factor_frame = _prepare_factors(factor_values)
    previous_weights: dict[str, float] = {}
    level = config.base_level
    level_rows: list[dict[str, object]] = []
    constituent_rows: list[dict[str, object]] = []

    for timestamp in rebalance_dates:
        timestamp = pd.Timestamp(timestamp)
        slice_bars = investable[investable["timestamp"] == timestamp].copy()
        if slice_bars.empty:
            continue
        weights = _compute_weights(config, slice_bars, factor_frame, timestamp)
        period_returns = returns[returns["timestamp"] == timestamp].set_index("instrument_id")["forward_return"]
        turnover = sum(abs(weights.get(instrument, 0.0) - previous_weights.get(instrument, 0.0)) for instrument in set(weights) | set(previous_weights))
        cost_return = turnover * config.cost_bps / 10_000
        index_return = sum(weight * float(period_returns.get(instrument, 0.0)) for instrument, weight in weights.items())
        net_return = index_return - cost_return
        level *= 1 + net_return
        level_rows.append(
            {
                "index_id": config.index_id,
                "timestamp": timestamp,
                "index_return": index_return,
                "cost_return": cost_return,
                "net_return": net_return,
                "turnover": turnover,
                "level": level,
            }
        )
        for instrument_id, weight in weights.items():
            row = slice_bars[slice_bars["instrument_id"] == instrument_id].iloc[0]
            constituent_rows.append(
                {
                    "index_id": config.index_id,
                    "timestamp": timestamp,
                    "instrument_id": instrument_id,
                    "asset_class": row["asset_class"],
                    "weight": weight,
                    "weighting_scheme": config.weighting_scheme.value,
                }
            )
        previous_weights = weights

    levels = pd.DataFrame(level_rows)
    constituents = pd.DataFrame(constituent_rows)
    metrics = _comparison_metrics(config, levels, benchmark)
    methodology = {
        "index_id": config.index_id,
        "name": config.name,
        "weighting_scheme": config.weighting_scheme.value,
        "rebalance_frequency": config.rebalance_frequency,
        "max_weight": config.max_weight,
        "cost_bps": config.cost_bps,
        "benchmark_id": config.benchmark_id,
        "rebalance_count": len(levels),
        "constituent_count": int(constituents["instrument_id"].nunique()) if not constituents.empty else 0,
        "asset_classes": sorted(constituents["asset_class"].unique().tolist()) if not constituents.empty else [],
    }
    return SyntheticIndexResult(
        config=config,
        levels=levels,
        constituents=constituents,
        benchmark=benchmark,
        metrics=metrics,
        methodology=methodology,
    )


def synthetic_universe_options(db_path: str | Path) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            """
            SELECT
                instrument_id,
                symbol,
                asset_class,
                COUNT(*) AS rows,
                MIN(timestamp) AS first_timestamp,
                MAX(timestamp) AS last_timestamp,
                AVG(volume) AS average_volume
            FROM market_bars
            GROUP BY instrument_id, symbol, asset_class
            ORDER BY asset_class, symbol
            """
        ).fetchdf()


def load_market_bars_for_index(
    db_path: str | Path,
    *,
    instrument_ids: list[str],
    benchmark_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    selected = [item for item in instrument_ids if item]
    if benchmark_id and benchmark_id not in selected:
        selected.append(benchmark_id)
    if not selected:
        raise ValueError("At least one constituent instrument is required.")
    target = initialize_duckdb(db_path)
    placeholders = ", ".join(["?"] * len(selected))
    clauses = [f"instrument_id IN ({placeholders})"]
    params: list[Any] = list(selected)
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT instrument_id, symbol, asset_class, timestamp, close, adj_close, volume
            FROM market_bars
            WHERE {" AND ".join(clauses)}
            ORDER BY instrument_id, timestamp
            """,
            params,
        ).fetchdf()


def run_synthetic_index_from_storage(
    db_path: str | Path,
    *,
    config: SyntheticIndexConfig,
    instrument_ids: list[str],
    start: str | None = None,
    end: str | None = None,
    factor_values: pd.DataFrame | None = None,
) -> SyntheticIndexResult:
    bars = load_market_bars_for_index(
        db_path,
        instrument_ids=instrument_ids,
        benchmark_id=config.benchmark_id,
        start=start,
        end=end,
    )
    if bars.empty:
        raise ValueError("No market_bars rows match the Synthetic Index Lab selection.")
    return build_synthetic_index(config, bars, factor_values=factor_values)


def _prepare_bars(market_bars: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    price_column = "adj_close" if "adj_close" in market_bars.columns else "close"
    required = {"instrument_id", "timestamp", "asset_class", "volume", price_column}
    missing = required.difference(market_bars.columns)
    if missing:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing)))
    bars = market_bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    bars[price_column] = pd.to_numeric(bars[price_column], errors="coerce")
    bars["volume"] = pd.to_numeric(bars["volume"], errors="coerce")
    bars = bars.dropna(subset=[price_column, "volume"])
    return bars.sort_values(["instrument_id", "timestamp"]).reset_index(drop=True), price_column


def _prepare_factors(factor_values: pd.DataFrame | None) -> pd.DataFrame | None:
    if factor_values is None:
        return None
    required = {"instrument_id", "timestamp", "factor_value"}
    missing = required.difference(factor_values.columns)
    if missing:
        raise ValueError("factor_values missing columns: " + ", ".join(sorted(missing)))
    frame = factor_values.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame


def _forward_returns(bars: pd.DataFrame, price_column: str) -> pd.DataFrame:
    frame = bars.copy()
    frame["forward_return"] = frame.groupby("instrument_id")[price_column].transform(
        lambda series: series.shift(-1) / series - 1
    )
    return frame.dropna(subset=["forward_return"]).reset_index(drop=True)


def _rebalance_dates(timestamps: list[pd.Timestamp], frequency: str) -> list[pd.Timestamp]:
    step = 1 if frequency == "1d" else int(frequency[:-1])
    return list(timestamps[::step])


def _compute_weights(
    config: SyntheticIndexConfig,
    slice_bars: pd.DataFrame,
    factor_frame: pd.DataFrame | None,
    timestamp: pd.Timestamp,
) -> dict[str, float]:
    if config.weighting_scheme == WeightingScheme.EQUAL_WEIGHT:
        raw = pd.Series(1.0, index=slice_bars["instrument_id"])
    elif config.weighting_scheme == WeightingScheme.LIQUIDITY_WEIGHT:
        raw = pd.Series(slice_bars["volume"].to_numpy(dtype=float), index=slice_bars["instrument_id"])
    elif config.weighting_scheme == WeightingScheme.FACTOR_TILT:
        if factor_frame is None:
            raise ValueError("factor_values are required for factor_tilt weighting")
        factors = factor_frame[factor_frame["timestamp"] == timestamp][["instrument_id", "factor_value"]]
        merged = slice_bars[["instrument_id"]].merge(factors, on="instrument_id", how="left")
        ranks = merged["factor_value"].rank(method="average", pct=True).fillna(0).to_numpy(dtype=float)
        raw = pd.Series(ranks, index=merged["instrument_id"])
    else:
        raise ValueError(f"unsupported weighting_scheme: {config.weighting_scheme}")
    raw = raw.clip(lower=0)
    if raw.sum() <= 0:
        raise ValueError("weighting inputs sum to zero")
    weights = raw / raw.sum()
    weights = _cap_and_renormalize(weights, config.max_weight)
    return {str(instrument): float(weight) for instrument, weight in weights.items()}


def _cap_and_renormalize(weights: pd.Series, max_weight: float) -> pd.Series:
    capped = weights.copy()
    for _ in range(10):
        over = capped > max_weight
        if not over.any():
            break
        excess = float((capped[over] - max_weight).sum())
        capped[over] = max_weight
        under = ~over
        if not under.any() or capped[under].sum() <= 0:
            break
        capped[under] += capped[under] / capped[under].sum() * excess
    return capped / capped.sum()


def _benchmark_series(config: SyntheticIndexConfig, bars: pd.DataFrame, price_column: str) -> pd.DataFrame:
    if not config.benchmark_id:
        return pd.DataFrame(columns=["benchmark_id", "timestamp", "benchmark_return", "benchmark_level"])
    benchmark = bars[bars["instrument_id"] == config.benchmark_id].copy()
    if benchmark.empty:
        raise ValueError(f"benchmark_id not found: {config.benchmark_id}")
    benchmark["benchmark_return"] = benchmark[price_column].shift(-1) / benchmark[price_column] - 1
    benchmark = benchmark.dropna(subset=["benchmark_return"])
    benchmark["benchmark_level"] = config.base_level * (1 + benchmark["benchmark_return"]).cumprod()
    benchmark["benchmark_id"] = config.benchmark_id
    return benchmark[["benchmark_id", "timestamp", "benchmark_return", "benchmark_level"]].reset_index(drop=True)


def _comparison_metrics(
    config: SyntheticIndexConfig,
    levels: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    index_cumulative = float(levels["level"].iloc[-1] / config.base_level - 1) if not levels.empty else 0.0
    rows.append({"metric_name": "index_cumulative_return", "metric_value": index_cumulative})
    rows.append({"metric_name": "average_turnover", "metric_value": float(levels["turnover"].mean()) if not levels.empty else 0.0})
    rows.append({"metric_name": "total_cost_return", "metric_value": float(levels["cost_return"].sum()) if not levels.empty else 0.0})
    if not benchmark.empty:
        benchmark_cumulative = float(benchmark["benchmark_level"].iloc[-1] / config.base_level - 1)
        rows.append({"metric_name": "benchmark_cumulative_return", "metric_value": benchmark_cumulative})
        rows.append({"metric_name": "excess_return", "metric_value": index_cumulative - benchmark_cumulative})
    return pd.DataFrame(rows)
