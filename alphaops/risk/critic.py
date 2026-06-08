"""Risk critic for alpha promotion and monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity
from alphaops.storage.duckdb import initialize_duckdb


@dataclass(frozen=True)
class RiskThresholds:
    max_drawdown: float = 0.2
    max_average_turnover: float = 1.5
    max_weight: float = 0.4
    min_quality_score: float = 0.8
    max_cost_ratio: float = 0.02
    max_stale_days: int = 5


@dataclass(frozen=True)
class RiskFinding:
    severity: str
    code: str
    message: str
    blocks_promotion: bool


@dataclass(frozen=True)
class RiskReview:
    alpha_id: str
    findings: list[RiskFinding]

    @property
    def blocks_promotion(self) -> bool:
        return any(finding.blocks_promotion for finding in self.findings)

    def summary(self) -> dict[str, object]:
        return {
            "alpha_id": self.alpha_id,
            "blocks_promotion": self.blocks_promotion,
            "finding_count": len(self.findings),
            "critical_count": sum(1 for finding in self.findings if finding.severity == "critical"),
            "findings": [finding.__dict__ for finding in self.findings],
        }


class RiskCritic:
    def __init__(self, thresholds: RiskThresholds | None = None) -> None:
        self.thresholds = thresholds or RiskThresholds()

    def review(
        self,
        *,
        alpha_id: str,
        metrics: dict[str, float],
        weights: pd.DataFrame,
        market_bars: pd.DataFrame,
        quality_score: float,
        lifecycle_state: LifecycleState,
        target_state: LifecycleState = LifecycleState.ACTIVE,
        as_of: datetime | None = None,
    ) -> RiskReview:
        findings: list[RiskFinding] = []
        findings.extend(self._drawdown(metrics))
        findings.extend(self._turnover(metrics))
        findings.extend(self._cost(metrics))
        findings.extend(self._concentration(weights))
        findings.extend(self._staleness(market_bars, as_of=as_of))
        findings.extend(self._quality(quality_score))
        findings.extend(self._lifecycle(lifecycle_state, target_state))
        return RiskReview(alpha_id=alpha_id, findings=findings)

    def _drawdown(self, metrics: dict[str, float]) -> list[RiskFinding]:
        drawdown = abs(float(metrics.get("max_drawdown", 0.0)))
        if drawdown > self.thresholds.max_drawdown:
            return [
                RiskFinding(
                    "critical",
                    "drawdown_limit",
                    f"max_drawdown {drawdown:.4f} exceeds limit {self.thresholds.max_drawdown:.4f}",
                    True,
                )
            ]
        return []

    def _turnover(self, metrics: dict[str, float]) -> list[RiskFinding]:
        turnover = float(metrics.get("average_turnover", 0.0))
        if turnover > self.thresholds.max_average_turnover:
            return [
                RiskFinding(
                    "warning",
                    "turnover_high",
                    f"average_turnover {turnover:.4f} exceeds limit {self.thresholds.max_average_turnover:.4f}",
                    False,
                )
            ]
        return []

    def _cost(self, metrics: dict[str, float]) -> list[RiskFinding]:
        total_cost = float(metrics.get("total_cost", 0.0))
        capital = float(metrics.get("initial_capital", 1.0))
        cost_ratio = total_cost / capital if capital else 0.0
        if cost_ratio > self.thresholds.max_cost_ratio:
            return [
                RiskFinding(
                    "warning",
                    "cost_sensitivity",
                    f"cost_ratio {cost_ratio:.4f} exceeds limit {self.thresholds.max_cost_ratio:.4f}",
                    False,
                )
            ]
        return []

    def _concentration(self, weights: pd.DataFrame) -> list[RiskFinding]:
        if weights.empty or "target_weight" not in weights.columns:
            return []
        max_abs = float(pd.to_numeric(weights["target_weight"], errors="coerce").abs().max())
        if max_abs > self.thresholds.max_weight:
            return [
                RiskFinding(
                    "critical",
                    "concentration_limit",
                    f"max absolute weight {max_abs:.4f} exceeds limit {self.thresholds.max_weight:.4f}",
                    True,
                )
            ]
        return []

    def _staleness(self, market_bars: pd.DataFrame, *, as_of: datetime | None) -> list[RiskFinding]:
        if market_bars.empty or "timestamp" not in market_bars.columns or as_of is None:
            return []
        latest = pd.to_datetime(market_bars["timestamp"]).max().to_pydatetime()
        stale_days = (as_of - latest).days
        if stale_days > self.thresholds.max_stale_days:
            return [
                RiskFinding(
                    "warning",
                    "stale_data",
                    f"latest data is {stale_days} days old",
                    False,
                )
            ]
        return []

    def _quality(self, quality_score: float) -> list[RiskFinding]:
        if quality_score < self.thresholds.min_quality_score:
            return [
                RiskFinding(
                    "critical",
                    "quality_score_low",
                    f"quality_score {quality_score:.4f} is below {self.thresholds.min_quality_score:.4f}",
                    True,
                )
            ]
        return []

    def _lifecycle(self, lifecycle_state: LifecycleState, target_state: LifecycleState) -> list[RiskFinding]:
        if target_state == LifecycleState.ACTIVE and lifecycle_state != LifecycleState.APPROVED:
            return [
                RiskFinding(
                    "critical",
                    "lifecycle_gate",
                    "activation requires approved lifecycle state",
                    True,
                )
            ]
        return []


def load_risk_context(db_path: str | Path, *, run_id: str, alpha_id: str | None = None) -> dict[str, Any]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        run = conn.execute(
            "SELECT run_id, alpha_id, initial_capital FROM backtest_runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if run is None:
            raise KeyError(f"backtest run not found: {run_id}")
        selected_alpha = alpha_id or run[1]
        metric_rows = conn.execute(
            "SELECT metric_name, metric_value FROM metric_results WHERE run_id = ?",
            [run_id],
        ).fetchall()
        metrics = {name: float(value) for name, value in metric_rows}
        metrics["initial_capital"] = float(run[2])
        weights = conn.execute(
            "SELECT run_id, timestamp, instrument_id, asset_class, target_weight FROM backtest_weights WHERE run_id = ?",
            [run_id],
        ).fetchdf()
        market_bars = conn.execute(
            """
            SELECT instrument_id, symbol, asset_class, timestamp, close, adj_close, volume, source_id
            FROM market_bars
            WHERE instrument_id IN (SELECT DISTINCT instrument_id FROM backtest_weights WHERE run_id = ?)
            ORDER BY instrument_id, timestamp
            """,
            [run_id],
        ).fetchdf()
        quality_score = conn.execute("SELECT AVG(quality_score) FROM quality_reports").fetchone()[0]
    registry = AlphaRegistry(target)
    try:
        lifecycle_state = registry.get_card(selected_alpha).lifecycle_state
    except KeyError:
        lifecycle_state = LifecycleState.REGISTRY_REVIEW
    return {
        "run_id": run_id,
        "alpha_id": selected_alpha,
        "metrics": metrics,
        "weights": weights,
        "market_bars": market_bars,
        "quality_score": float(quality_score) if quality_score is not None else 1.0,
        "lifecycle_state": lifecycle_state,
    }


def run_risk_review_from_storage(
    db_path: str | Path,
    *,
    run_id: str,
    alpha_id: str | None = None,
    thresholds: RiskThresholds | None = None,
    target_state: LifecycleState = LifecycleState.ACTIVE,
    as_of: datetime | None = None,
    persist_flags: bool = True,
) -> dict[str, Any]:
    context = load_risk_context(db_path, run_id=run_id, alpha_id=alpha_id)
    review = RiskCritic(thresholds).review(
        alpha_id=str(context["alpha_id"]),
        metrics=dict(context["metrics"]),
        weights=context["weights"],
        market_bars=context["market_bars"],
        quality_score=float(context["quality_score"]),
        lifecycle_state=context["lifecycle_state"],
        target_state=target_state,
        as_of=as_of,
    )
    persisted = 0
    if persist_flags:
        registry = AlphaRegistry(initialize_duckdb(db_path))
        for finding in review.findings:
            registry.add_risk_flag(
                review.alpha_id,
                RiskFlag(RiskSeverity(finding.severity), finding.code, finding.message),
            )
            persisted += 1
    return {"review": review, "context": context, "persisted_flags": persisted}
