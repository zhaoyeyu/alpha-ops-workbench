"""Information coefficient and RankIC calculations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


def align_forward_returns(
    factor_values: pd.DataFrame,
    market_bars: pd.DataFrame,
    *,
    horizon: int = 1,
    price_column: str = "adj_close",
) -> pd.DataFrame:
    """Align factor observations with future instrument returns."""

    if horizon <= 0:
        raise ValueError("horizon must be positive")
    factor_required = {"alpha_id", "instrument_id", "timestamp", "factor_value"}
    bar_required = {"instrument_id", "timestamp", price_column}
    if not bar_required.issubset(market_bars.columns) and price_column == "adj_close":
        bar_required = {"instrument_id", "timestamp", "close"}
        price_column = "close"
    missing_factor = factor_required.difference(factor_values.columns)
    missing_bars = bar_required.difference(market_bars.columns)
    if missing_factor:
        raise ValueError("factor_values missing columns: " + ", ".join(sorted(missing_factor)))
    if missing_bars:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing_bars)))

    bars = market_bars.copy()
    factors = factor_values.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    factors["timestamp"] = pd.to_datetime(factors["timestamp"])
    bars = bars.sort_values(["instrument_id", "timestamp"]).reset_index(drop=True)
    bars["_price"] = pd.to_numeric(bars[price_column], errors="coerce")
    bars["forward_return"] = bars.groupby("instrument_id")["_price"].transform(
        lambda series: series.shift(-horizon) / series - 1
    )
    join_columns = ["instrument_id", "timestamp", "forward_return"]
    optional_columns = [
        column
        for column in ["asset_class", "symbol", "exchange", "currency"]
        if column in bars.columns and column not in factors.columns
    ]
    aligned = factors.merge(bars[join_columns + optional_columns], on=["instrument_id", "timestamp"], how="left")
    return aligned.dropna(subset=["factor_value", "forward_return"]).reset_index(drop=True)


def compute_ic_by_date(
    aligned: pd.DataFrame,
    *,
    group_column: str | None = None,
) -> pd.DataFrame:
    """Compute by-date Pearson IC and Spearman RankIC."""

    required = {"alpha_id", "timestamp", "factor_value", "forward_return"}
    missing = required.difference(aligned.columns)
    if missing:
        raise ValueError("aligned frame missing columns: " + ", ".join(sorted(missing)))

    frame = aligned.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["factor_value"] = pd.to_numeric(frame["factor_value"], errors="coerce")
    frame["forward_return"] = pd.to_numeric(frame["forward_return"], errors="coerce")
    frame = frame.dropna(subset=["factor_value", "forward_return"])
    group_keys = ["alpha_id", "timestamp"]
    if group_column:
        if group_column not in frame.columns:
            raise ValueError(f"group_column is not available: {group_column}")
        group_keys.append(group_column)

    rows: list[dict[str, object]] = []
    for keys, group in frame.groupby(group_keys, sort=True):
        if len(group) < 2:
            ic = float("nan")
            rank_ic = float("nan")
        else:
            ic = _safe_correlation(group["factor_value"], group["forward_return"])
            rank_ic = _rank_correlation(group["factor_value"], group["forward_return"])
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {
            "alpha_id": keys[0],
            "timestamp": keys[1],
            "group": keys[2] if group_column else "all",
            "ic": ic,
            "rank_ic": rank_ic,
            "observation_count": int(len(group)),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _rank_correlation(left: pd.Series, right: pd.Series) -> float:
    left_rank = left.rank(method="average")
    right_rank = right.rank(method="average")
    return _safe_correlation(left_rank, right_rank)


def _safe_correlation(left: pd.Series, right: pd.Series) -> float:
    if left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return float("nan")
    return float(left.corr(right, method="pearson"))


def summarize_ic(ic_by_date: pd.DataFrame, *, alpha_id: str) -> pd.DataFrame:
    """Summarize IC and RankIC with t-stat style diagnostics."""

    required = {"ic", "rank_ic"}
    missing = required.difference(ic_by_date.columns)
    if missing:
        raise ValueError("ic_by_date missing columns: " + ", ".join(sorted(missing)))
    ic_values = pd.to_numeric(ic_by_date["ic"], errors="coerce").dropna()
    rank_values = pd.to_numeric(ic_by_date["rank_ic"], errors="coerce").dropna()
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def _mean(values: pd.Series) -> float:
        return float(values.mean()) if not values.empty else float("nan")

    def _std(values: pd.Series) -> float:
        return float(values.std(ddof=1)) if len(values) > 1 else 0.0

    def _t_stat(values: pd.Series) -> float:
        if values.empty:
            return float("nan")
        std = _std(values)
        if std == 0:
            return 0.0
        return float(values.mean() / (std / (len(values) ** 0.5)))

    metrics = {
        "ic_mean": _mean(ic_values),
        "ic_std": _std(ic_values),
        "ic_t_stat": _t_stat(ic_values),
        "rank_ic_mean": _mean(rank_values),
        "rank_ic_std": _std(rank_values),
        "rank_ic_t_stat": _t_stat(rank_values),
        "period_count": float(len(ic_values)),
    }
    return pd.DataFrame(
        [
            {
                "alpha_id": alpha_id,
                "metric_name": name,
                "metric_value": value,
                "created_at": created_at,
            }
            for name, value in metrics.items()
        ]
    )


def persist_ic_summary(
    db_path: str | Path,
    summary: pd.DataFrame,
    *,
    run_id: str,
    frequency: str = "1d",
) -> int:
    """Persist IC summary metrics for registry/report consumption."""

    required = {"alpha_id", "metric_name", "metric_value", "created_at"}
    missing = required.difference(summary.columns)
    if missing:
        raise ValueError("summary missing columns: " + ", ".join(sorted(missing)))
    if summary.empty:
        return 0
    frame = pd.DataFrame(
        {
            "run_id": run_id,
            "scope_id": summary["alpha_id"],
            "metric_name": summary["metric_name"],
            "metric_value": summary["metric_value"],
            "frequency": frequency,
            "created_at": summary["created_at"],
        }
    )
    with duckdb.connect(str(db_path)) as conn:
        conn.register("ic_summary_frame", frame)
        conn.execute(
            """
            INSERT OR REPLACE INTO metric_results
            SELECT run_id, scope_id, metric_name, metric_value, frequency, created_at
            FROM ic_summary_frame
            """
        )
    return len(frame)
