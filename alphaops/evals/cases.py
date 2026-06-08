"""Deterministic evaluation case runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import duckdb
import pandas as pd

from alphaops.lifecycle.rules import LifecycleState
from alphaops.reports.renderer import render_report
from alphaops.risk.critic import RiskCritic, RiskThresholds
from alphaops.tools.registry import default_tool_registry
from alphaops.storage.duckdb import initialize_duckdb


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    category: str
    description: str
    check: Callable[[], bool]


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    category: str
    status: str
    created_at: datetime


class EvaluationRunner:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = initialize_duckdb(db_path) if db_path else None

    def run(self, cases: list[EvaluationCase]) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []
        for case in cases:
            status = "passed" if case.check() else "failed"
            results.append(
                EvaluationResult(
                    case_id=case.case_id,
                    category=case.category,
                    status=status,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
        self.persist(results)
        return results

    def persist(self, results: list[EvaluationResult]) -> None:
        if self.db_path is None or not results:
            return
        frame = pd.DataFrame([result.__dict__ for result in results])
        with duckdb.connect(str(self.db_path)) as conn:
            conn.register("evaluation_frame", frame)
            conn.execute("INSERT OR REPLACE INTO evaluation_cases SELECT case_id, category, status, created_at FROM evaluation_frame")


def built_in_cases() -> list[EvaluationCase]:
    return [
        EvaluationCase("schema_tool_registry", "schema_validity", "Tool registry exposes required schemas", _case_tool_schema),
        EvaluationCase("tool_factor_success", "tool_success", "Factor tool succeeds on real bars", _case_factor_tool),
        EvaluationCase("repro_factor_output", "reproducibility", "Factor output is reproducible", _case_reproducibility),
        EvaluationCase("report_completeness", "report_completeness", "Report includes sources and reproducibility", _case_report),
        EvaluationCase("risk_flag_coverage", "risk_flag_coverage", "Risk critic emits expected critical flags", _case_risk_flags),
    ]


def evaluation_case_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"case_id": case.case_id, "category": case.category, "description": case.description}
            for case in built_in_cases()
        ]
    )


def run_evaluation_cases(db_path: str | Path, *, case_ids: list[str] | None = None) -> list[EvaluationResult]:
    cases = built_in_cases()
    if case_ids:
        wanted = set(case_ids)
        cases = [case for case in cases if case.case_id in wanted]
    if not cases:
        raise ValueError("No evaluation cases selected.")
    return EvaluationRunner(initialize_duckdb(db_path)).run(cases)


def list_evaluation_results(db_path: str | Path) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            """
            SELECT case_id, category, status, created_at
            FROM evaluation_cases
            ORDER BY created_at DESC, case_id
            """
        ).fetchdf()


def _case_tool_schema() -> bool:
    names = {definition.name for definition in default_tool_registry().definitions()}
    required = {"quant.factor.evaluate", "quant.backtest.run", "registry.transition", "llm.openrouter.request"}
    return required.issubset(names)


def _case_factor_tool() -> bool:
    result = default_tool_registry().call(
        "quant.factor.evaluate",
        {"alpha_id": "eval_alpha", "formula": "rank(close)", "market_bars": _bars()},
    )
    return bool(result.output["records"])


def _case_reproducibility() -> bool:
    registry = default_tool_registry()
    payload = {"alpha_id": "eval_alpha", "formula": "rank(close)", "market_bars": _bars()}
    first = registry.call("quant.factor.evaluate", payload).output["records"]
    second = registry.call("quant.factor.evaluate", payload).output["records"]
    return first == second


def _case_report() -> bool:
    report = render_report(
        report_id="eval_report",
        title="Eval Report",
        sections={"Metrics": {"rank_ic_mean": 0.1}},
        source_links=["tool:quant.factor.evaluate"],
        reproducibility={"case_id": "report_completeness"},
    )
    return "## Sources" in report.markdown and "## Reproducibility" in report.markdown and "rank_ic_mean" in report.markdown


def _case_risk_flags() -> bool:
    review = RiskCritic(RiskThresholds(max_drawdown=0.1)).review(
        alpha_id="eval_alpha",
        metrics={"max_drawdown": -0.2, "average_turnover": 0, "total_cost": 0, "initial_capital": 100},
        weights=pd.DataFrame([{"target_weight": 0.1}]),
        market_bars=pd.DataFrame([{"timestamp": datetime(2026, 1, 1)}]),
        quality_score=1.0,
        lifecycle_state=LifecycleState.APPROVED,
        target_state=LifecycleState.ACTIVE,
    )
    return any(finding.code == "drawdown_limit" and finding.blocks_promotion for finding in review.findings)


def _bars() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for instrument_id, prices in {"eq:a": [100, 110], "eq:b": [100, 120]}.items():
        for day, price in enumerate(prices, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "asset_class": "equity",
                    "timestamp": datetime(2026, 1, day),
                    "close": float(price),
                    "adj_close": float(price),
                    "volume": 1000,
                }
            )
    return rows
