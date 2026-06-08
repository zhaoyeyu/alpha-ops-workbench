"""Registry of typed tools exposed to agent orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd
from pydantic import ValidationError

from alphaops.data.quality import profile_market_bars
from alphaops.data.contracts import BacktestContract
from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity
from alphaops.quant.backtest import run_backtest
from alphaops.quant.evaluation import evaluate_alpha_ic
from alphaops.quant.factors import evaluate_formula
from alphaops.tools.schema import (
    OpenRouterRequest,
    ToolCallError,
    ToolCategory,
    ToolDefinition,
    ToolResult,
    openrouter_financial_data_guard,
)


ToolHandler = Callable[[dict[str, Any]], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def definition(self, name: str) -> ToolDefinition:
        return self._definitions[name]

    def call(self, name: str, payload: dict[str, Any]) -> ToolResult:
        if name not in self._handlers:
            raise ToolCallError(f"unknown tool: {name}")
        return self._handlers[name](payload)


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="data_quality.profile_market_bars",
            category=ToolCategory.DATA,
            deterministic=True,
            description="Profile canonical market bars through the deterministic data quality engine.",
        ),
        data_quality_profile_tool,
    )
    registry.register(
        ToolDefinition(
            name="quant.factor.evaluate",
            category=ToolCategory.QUANT,
            deterministic=True,
            description="Evaluate Alpha DSL formula through the deterministic factor engine.",
        ),
        factor_evaluate_tool,
    )
    registry.register(
        ToolDefinition(
            name="quant.backtest.run",
            category=ToolCategory.QUANT,
            deterministic=True,
            description="Run deterministic research backtest from contract, factor values, and bars.",
        ),
        backtest_run_tool,
    )
    registry.register(
        ToolDefinition(
            name="registry.transition",
            category=ToolCategory.REGISTRY,
            deterministic=True,
            description="Transition a persisted alpha registry record using lifecycle rules.",
        ),
        registry_transition_tool,
    )
    registry.register(
        ToolDefinition(
            name="risk.review_alpha",
            category=ToolCategory.RISK,
            deterministic=True,
            description="Review alpha metrics and create deterministic risk flags.",
        ),
        risk_review_tool,
    )
    registry.register(
        ToolDefinition(
            name="report.render_alpha_card",
            category=ToolCategory.REPORT,
            deterministic=True,
            description="Render a deterministic alpha card report from persisted registry data.",
        ),
        report_render_tool,
    )
    registry.register(
        ToolDefinition(
            name="evaluation.ic_run",
            category=ToolCategory.EVALUATION,
            deterministic=True,
            description="Run deterministic IC/RankIC evaluation from factor values and bars.",
        ),
        evaluation_ic_tool,
    )
    registry.register(
        ToolDefinition(
            name="llm.openrouter.request",
            category=ToolCategory.LLM_GATEWAY,
            deterministic=False,
            description="Build an OpenRouter LLM gateway request for planning/formula/report/research workflows only.",
        ),
        openrouter_request_tool,
    )
    return registry


def data_quality_profile_tool(payload: dict[str, Any]) -> ToolResult:
    frame = pd.DataFrame(payload["market_bars"])
    report = profile_market_bars(frame, dataset_id=str(payload.get("dataset_id", "tool_dataset")))
    return _result(
        "data_quality.profile_market_bars",
        {
            "report_id": report.report_id,
            "quality_score": report.quality_score,
            "row_count": report.row_count,
            "issues": [issue.model_dump() for issue in report.issues],
        },
        deterministic=True,
        service="alphaops.data.quality.profile_market_bars",
    )


def factor_evaluate_tool(payload: dict[str, Any]) -> ToolResult:
    result = evaluate_formula(
        str(payload["formula"]),
        pd.DataFrame(payload["market_bars"]),
        alpha_id=str(payload["alpha_id"]),
    )
    return _result(
        "quant.factor.evaluate",
        {
            "alpha_id": result.alpha_id,
            "records": result.values.to_dict(orient="records"),
            "registry_payload": result.for_alpha_registry(),
        },
        deterministic=True,
        service="alphaops.quant.factors.evaluate_formula",
    )


def backtest_run_tool(payload: dict[str, Any]) -> ToolResult:
    contract = BacktestContract(**payload["contract"])
    result = run_backtest(
        contract,
        pd.DataFrame(payload["factor_values"]),
        pd.DataFrame(payload["market_bars"]),
        run_id=str(payload["run_id"]),
        initial_capital=float(payload.get("initial_capital", 1_000_000.0)),
    )
    return _result(
        "quant.backtest.run",
        {
            "run_id": result.run_id,
            "metrics": dict(zip(result.metrics["metric_name"], result.metrics["metric_value"], strict=True)),
            "weights_rows": len(result.weights),
            "trades_rows": len(result.trades),
            "equity_rows": len(result.equity_curve),
        },
        deterministic=True,
        service="alphaops.quant.backtest.run_backtest",
    )


def registry_transition_tool(payload: dict[str, Any]) -> ToolResult:
    registry = AlphaRegistry(Path(payload["db_path"]))
    card = registry.transition(
        str(payload["alpha_id"]),
        LifecycleState(str(payload["target_state"])),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        report_link=payload.get("report_link"),
    )
    return _result(
        "registry.transition",
        {"alpha_id": card.alpha_id, "lifecycle_state": card.lifecycle_state.value, "report_links": card.report_links},
        deterministic=True,
        service="alphaops.lifecycle.registry.AlphaRegistry.transition",
    )


def risk_review_tool(payload: dict[str, Any]) -> ToolResult:
    metrics = {str(key): float(value) for key, value in dict(payload["metrics"]).items()}
    flags: list[RiskFlag] = []
    if metrics.get("rank_ic_mean", 0.0) < 0:
        flags.append(RiskFlag(RiskSeverity.WARNING, "negative_rank_ic", "RankIC is negative"))
    if abs(metrics.get("max_drawdown", 0.0)) > float(payload.get("max_drawdown_limit", 0.2)):
        flags.append(RiskFlag(RiskSeverity.CRITICAL, "drawdown_limit", "Drawdown exceeds configured limit"))
    return _result(
        "risk.review_alpha",
        {"flags": [{"severity": flag.severity.value, "code": flag.code, "message": flag.message} for flag in flags]},
        deterministic=True,
        service="alphaops.lifecycle.rules",
    )


def report_render_tool(payload: dict[str, Any]) -> ToolResult:
    registry = AlphaRegistry(Path(payload["db_path"]))
    card = registry.get_card(str(payload["alpha_id"]))
    lines = [
        f"# Alpha {card.alpha_id}",
        f"Formula: {card.formula}",
        f"State: {card.lifecycle_state.value}",
        "Metrics:",
    ]
    lines.extend(f"- {name}: {value:.6f}" for name, value in sorted(card.metrics.items()))
    report = "\n".join(lines)
    return _result(
        "report.render_alpha_card",
        {"alpha_id": card.alpha_id, "markdown": report},
        deterministic=True,
        service="alphaops.lifecycle.registry.AlphaRegistry.get_card",
    )


def evaluation_ic_tool(payload: dict[str, Any]) -> ToolResult:
    result = evaluate_alpha_ic(
        pd.DataFrame(payload["factor_values"]),
        pd.DataFrame(payload["market_bars"]),
        alpha_id=str(payload["alpha_id"]),
        horizon=int(payload.get("horizon", 1)),
    )
    return _result(
        "evaluation.ic_run",
        {"summary": dict(zip(result.summary["metric_name"], result.summary["metric_value"], strict=True))},
        deterministic=True,
        service="alphaops.quant.evaluation.evaluate_alpha_ic",
    )


def openrouter_request_tool(payload: dict[str, Any]) -> ToolResult:
    openrouter_financial_data_guard(payload)
    try:
        request = OpenRouterRequest(**payload["request"])
    except ValidationError as exc:
        raise ToolCallError(str(exc)) from exc
    return _result(
        "llm.openrouter.request",
        {"request": request.model_dump(), "gateway": "openrouter", "is_financial_data_source": False},
        deterministic=False,
        service="openrouter_llm_gateway",
    )


def _result(tool_name: str, output: dict[str, Any], *, deterministic: bool, service: str) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        output=output,
        audit={"deterministic": deterministic, "service": service, "agent_direct_metric_calculation": False},
    )
