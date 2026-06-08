"""Alpha evaluation workflows built on deterministic quant primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alphaops.quant.ic import align_forward_returns, compute_ic_by_date, persist_ic_summary, summarize_ic


@dataclass(frozen=True)
class AlphaEvaluationResult:
    alpha_id: str
    aligned: pd.DataFrame
    by_date: pd.DataFrame
    summary: pd.DataFrame

    def for_alpha_registry(self) -> dict[str, object]:
        return {
            "alpha_id": self.alpha_id,
            "metrics": dict(zip(self.summary["metric_name"], self.summary["metric_value"], strict=True)),
            "periods": int(
                self.summary.loc[self.summary["metric_name"] == "period_count", "metric_value"].iloc[0]
            ),
        }

    def for_report(self) -> dict[str, object]:
        return {
            "alpha_id": self.alpha_id,
            "by_date_rows": len(self.by_date),
            "summary": self.for_alpha_registry()["metrics"],
        }

    def persist(self, db_path: str | Path, *, run_id: str, frequency: str = "1d") -> int:
        return persist_ic_summary(db_path, self.summary, run_id=run_id, frequency=frequency)


def evaluate_alpha_ic(
    factor_values: pd.DataFrame,
    market_bars: pd.DataFrame,
    *,
    alpha_id: str,
    horizon: int = 1,
    price_column: str = "adj_close",
    group_column: str | None = None,
) -> AlphaEvaluationResult:
    """Run forward-return alignment, IC/RankIC, and summary for one alpha."""

    aligned = align_forward_returns(
        factor_values,
        market_bars,
        horizon=horizon,
        price_column=price_column,
    )
    by_date = compute_ic_by_date(aligned, group_column=group_column)
    summary = summarize_ic(by_date, alpha_id=alpha_id)
    return AlphaEvaluationResult(alpha_id=alpha_id, aligned=aligned, by_date=by_date, summary=summary)
