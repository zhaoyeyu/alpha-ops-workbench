"""Return series calculations and persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


def _select_price_column(bars: pd.DataFrame, preferred: str) -> str:
    if preferred in bars.columns and bars[preferred].notna().any():
        return preferred
    if "close" in bars.columns:
        return "close"
    raise ValueError("bars must include close or the preferred price column")


def compute_adjusted_returns(
    market_bars: pd.DataFrame,
    *,
    price_column: str = "adj_close",
    run_id: str = "research_run",
) -> pd.DataFrame:
    """Compute deterministic instrument-level returns from canonical bars."""

    required = {"instrument_id", "asset_class", "timestamp", "frequency", "source_id"}
    missing = required.difference(market_bars.columns)
    if missing:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing)))

    selected_price_column = _select_price_column(market_bars, price_column)
    frame = market_bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["_price"] = pd.to_numeric(frame[selected_price_column], errors="coerce")
    frame = frame.dropna(subset=["_price"])
    if frame.empty:
        raise ValueError("no valid prices available for return calculation")

    frame = frame.sort_values(["instrument_id", "timestamp"])
    frame["return_value"] = frame.groupby("instrument_id")["_price"].pct_change()
    frame = frame.dropna(subset=["return_value"]).copy()
    frame["cumulative_return"] = (
        frame.groupby("instrument_id")["return_value"].transform(lambda values: (1 + values).cumprod() - 1)
    )
    frame["run_id"] = run_id
    frame["price_column"] = selected_price_column
    frame["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    return frame[
        [
            "run_id",
            "instrument_id",
            "asset_class",
            "timestamp",
            "frequency",
            "return_value",
            "cumulative_return",
            "price_column",
            "source_id",
            "created_at",
        ]
    ].reset_index(drop=True)


def compute_benchmark_returns(
    returns: pd.DataFrame,
    benchmark_instrument_id: str,
) -> pd.DataFrame:
    """Extract a benchmark return series from computed instrument returns."""

    required = {"instrument_id", "timestamp", "return_value", "cumulative_return"}
    missing = required.difference(returns.columns)
    if missing:
        raise ValueError("returns missing columns: " + ", ".join(sorted(missing)))
    benchmark = returns[returns["instrument_id"] == benchmark_instrument_id].copy()
    if benchmark.empty:
        raise ValueError(f"benchmark instrument not found: {benchmark_instrument_id}")
    return benchmark.sort_values("timestamp").reset_index(drop=True)


def persist_return_series(db_path: str | Path, returns: pd.DataFrame) -> int:
    """Persist computed returns into DuckDB."""

    columns = [
        "run_id",
        "instrument_id",
        "asset_class",
        "timestamp",
        "frequency",
        "return_value",
        "cumulative_return",
        "price_column",
        "source_id",
        "created_at",
    ]
    missing = set(columns).difference(returns.columns)
    if missing:
        raise ValueError("returns missing columns: " + ", ".join(sorted(missing)))
    if returns.empty:
        return 0
    frame = returns[columns].copy()
    frame["asset_class"] = frame["asset_class"].astype(str)
    frame["frequency"] = frame["frequency"].astype(str)
    with duckdb.connect(str(db_path)) as conn:
        conn.register("returns_frame", frame)
        conn.execute(
            """
            INSERT OR REPLACE INTO return_series
            SELECT run_id, instrument_id, asset_class, timestamp, frequency, return_value,
                   cumulative_return, price_column, source_id, created_at
            FROM returns_frame
            """
        )
    return len(frame)

