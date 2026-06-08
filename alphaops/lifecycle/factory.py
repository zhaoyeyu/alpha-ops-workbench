"""Alpha Factory workflows backed by DSL, factor, and IC engines."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass
from alphaops.quant.evaluation import AlphaEvaluationResult, evaluate_alpha_ic
from alphaops.quant.factors import FactorEvaluationResult, evaluate_formula
from alphaops.storage.duckdb import initialize_duckdb
from alphaops.lifecycle.registry import AlphaCard, AlphaRegistry


def normalize_formula(formula: str) -> str:
    return " ".join(formula.strip().split())


def candidate_id_for_formula(formula: str) -> str:
    digest = hashlib.sha256(normalize_formula(formula).encode("utf-8")).hexdigest()[:16]
    return f"alpha_{digest}"


@dataclass(frozen=True)
class AlphaCandidate:
    candidate_id: str
    formula: str
    state: str
    dependencies: tuple[str, ...]
    operator_names: tuple[str, ...]
    factor_preview: pd.DataFrame
    evaluation: AlphaEvaluationResult
    score: float
    duplicate_of: str | None = None

    def registry_review_payload(self) -> dict[str, object]:
        return {
            "alpha_id": self.candidate_id,
            "formula": self.formula,
            "ast_version": "0.1",
            "lifecycle_state": "registry_review",
            "dependencies": list(self.dependencies),
            "operator_names": list(self.operator_names),
            "score": self.score,
            "metrics": self.evaluation.for_alpha_registry()["metrics"],
            "duplicate_of": self.duplicate_of,
        }


class AlphaFactory:
    """Create and score alpha candidates from validated formulas."""

    def __init__(self) -> None:
        self._formula_to_candidate: dict[str, str] = {}

    def create_candidate(
        self,
        formula: str,
        market_bars: pd.DataFrame,
        *,
        horizon: int = 1,
        preview_rows: int = 10,
    ) -> AlphaCandidate:
        normalized = normalize_formula(formula)
        candidate_id = candidate_id_for_formula(normalized)
        factor_result = evaluate_formula(normalized, market_bars, alpha_id=candidate_id)
        evaluation = evaluate_alpha_ic(
            factor_result.for_ic_analysis(),
            market_bars,
            alpha_id=candidate_id,
            horizon=horizon,
        )
        duplicate_of = self._formula_to_candidate.get(normalized)
        state = "duplicate" if duplicate_of else "registry_review"
        if duplicate_of is None:
            self._formula_to_candidate[normalized] = candidate_id
        score = score_candidate(evaluation)
        return AlphaCandidate(
            candidate_id=candidate_id,
            formula=normalized,
            state=state,
            dependencies=factor_result.expression.dependencies,
            operator_names=factor_result.expression.operator_names,
            factor_preview=factor_result.values.head(preview_rows).copy(),
            evaluation=evaluation,
            score=score,
            duplicate_of=duplicate_of,
        )


def load_factory_market_bars(
    db_path: str | Path,
    *,
    asset_class: AssetClass | None = None,
    symbol: str | None = None,
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if asset_class:
        clauses.append("asset_class = ?")
        params.append(asset_class.value)
    if symbol:
        clauses.append("upper(symbol) = upper(?)")
        params.append(symbol)
    if source_id:
        clauses.append("source_id = ?")
        params.append(source_id)
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT instrument_id, symbol, asset_class, timestamp, close, adj_close, volume, source_id
            FROM market_bars
            {where_sql}
            ORDER BY instrument_id, timestamp
            """,
            params,
        ).fetchdf()


def create_alpha_candidate_from_storage(
    db_path: str | Path,
    *,
    formula: str,
    asset_class: AssetClass | None = None,
    symbol: str | None = None,
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    horizon: int = 1,
    register_for_review: bool = True,
) -> dict[str, object]:
    bars = load_factory_market_bars(
        db_path,
        asset_class=asset_class,
        symbol=symbol,
        source_id=source_id,
        start=start,
        end=end,
    )
    if bars.empty:
        raise ValueError("No market_bars rows match the Alpha Factory selection.")
    candidate = AlphaFactory().create_candidate(formula, bars, horizon=horizon)
    payload = candidate.registry_review_payload()
    card: AlphaCard | None = None
    if register_for_review and candidate.state != "duplicate":
        card = AlphaRegistry(initialize_duckdb(db_path)).register_for_review(payload)
    return {"candidate": candidate, "payload": payload, "card": card, "market_bars": bars}


def score_candidate(evaluation: AlphaEvaluationResult) -> float:
    metrics = dict(zip(evaluation.summary["metric_name"], evaluation.summary["metric_value"], strict=True))
    ic_mean = float(metrics.get("ic_mean", 0.0))
    rank_ic_mean = float(metrics.get("rank_ic_mean", 0.0))
    period_count = float(metrics.get("period_count", 0.0))
    sample_penalty = 1.0 if period_count >= 2 else 0.5
    return (0.5 * ic_mean + 0.5 * rank_ic_mean) * sample_penalty
