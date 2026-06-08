"""Research metrics computed from deterministic return series."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


PERIODS_PER_YEAR = {
    "1d": 252,
    "1h": 252 * 6.5,
    "1m": 252 * 390,
}


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Return drawdown path from a simple return series."""

    cumulative = (1 + returns.fillna(0)).cumprod()
    running_peak = cumulative.cummax()
    return cumulative / running_peak - 1


def compute_performance_metrics(
    returns: pd.DataFrame,
    *,
    run_id: str,
    scope_id: str,
    return_column: str = "return_value",
    frequency: str = "1d",
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Compute cumulative return, volatility, drawdown, and Sharpe-like metrics."""

    if return_column not in returns.columns:
        raise ValueError(f"returns missing column: {return_column}")
    values = pd.to_numeric(returns[return_column], errors="coerce").dropna()
    if values.empty:
        raise ValueError("no valid returns available for metric calculation")

    periods = PERIODS_PER_YEAR.get(frequency, 252)
    cumulative_return = float((1 + values).prod() - 1)
    volatility = float(values.std(ddof=0) * (periods**0.5))
    excess_mean = float(values.mean() - risk_free_rate / periods)
    sharpe_like = 0.0 if volatility == 0 else float((excess_mean * periods) / volatility)
    max_drawdown = float(drawdown_series(values).min())
    hit_rate = float((values > 0).mean())

    created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    metrics = {
        "cumulative_return": cumulative_return,
        "annualized_volatility": volatility,
        "max_drawdown": max_drawdown,
        "sharpe_like": sharpe_like,
        "hit_rate": hit_rate,
        "observation_count": float(len(values)),
    }
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "scope_id": scope_id,
                "metric_name": name,
                "metric_value": value,
                "frequency": frequency,
                "created_at": created_at,
            }
            for name, value in metrics.items()
        ]
    )


def persist_metric_results(db_path: str | Path, metrics: pd.DataFrame) -> int:
    """Persist metric results into DuckDB."""

    columns = ["run_id", "scope_id", "metric_name", "metric_value", "frequency", "created_at"]
    missing = set(columns).difference(metrics.columns)
    if missing:
        raise ValueError("metrics missing columns: " + ", ".join(sorted(missing)))
    if metrics.empty:
        return 0
    frame = metrics[columns].copy()
    with duckdb.connect(str(db_path)) as conn:
        conn.register("metrics_frame", frame)
        conn.execute(
            """
            INSERT OR REPLACE INTO metric_results
            SELECT run_id, scope_id, metric_name, metric_value, frequency, created_at
            FROM metrics_frame
            """
        )
    return len(frame)
