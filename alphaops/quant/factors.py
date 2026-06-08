"""Deterministic factor engine for Alpha DSL expressions."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from alphaops.quant.alpha_dsl import (
    AlphaDslError,
    AlphaExpression,
    BinaryOpNode,
    CallNode,
    DslNode,
    FieldNode,
    NumberNode,
    compile_formula,
)


@dataclass(frozen=True)
class FactorEvaluationResult:
    alpha_id: str
    expression: AlphaExpression
    values: pd.DataFrame

    def for_ic_analysis(self) -> pd.DataFrame:
        return self.values[["alpha_id", "instrument_id", "timestamp", "factor_value"]].copy()

    def for_backtest(self) -> pd.DataFrame:
        return self.values[["alpha_id", "instrument_id", "timestamp", "factor_value"]].copy()

    def for_alpha_registry(self) -> dict[str, object]:
        return {
            "alpha_id": self.alpha_id,
            "formula": self.expression.formula,
            "ast_version": "0.1",
            "dependencies": list(self.expression.dependencies),
            "operator_names": list(self.expression.operator_names),
        }


def evaluate_formula(
    formula: str,
    market_bars: pd.DataFrame,
    *,
    alpha_id: str,
) -> FactorEvaluationResult:
    """Compile and evaluate a DSL formula against canonical market bars."""

    required = {"instrument_id", "timestamp"}
    missing = required.difference(market_bars.columns)
    if missing:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing)))

    frame = market_bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame = frame.sort_values(["instrument_id", "timestamp"]).reset_index(drop=True)
    expression = compile_formula(formula, available_fields=set(frame.columns))
    series = _evaluate_node(expression.ast, frame)
    values = frame[["instrument_id", "timestamp"]].copy()
    values["alpha_id"] = alpha_id
    values["factor_value"] = pd.to_numeric(series, errors="coerce")
    values = values[["alpha_id", "instrument_id", "timestamp", "factor_value"]]
    return FactorEvaluationResult(alpha_id=alpha_id, expression=expression, values=values)


def _evaluate_node(node: DslNode, frame: pd.DataFrame) -> pd.Series:
    if isinstance(node, NumberNode):
        return pd.Series(node.value, index=frame.index)
    if isinstance(node, FieldNode):
        if node.name not in frame.columns:
            raise AlphaDslError("unknown_field", f"field is not available in input data: {node.name}", node=node.name)
        return frame[node.name]
    if isinstance(node, BinaryOpNode):
        left = pd.to_numeric(_evaluate_node(node.left, frame), errors="coerce")
        right = pd.to_numeric(_evaluate_node(node.right, frame), errors="coerce")
        if node.operator == "add":
            return left + right
        if node.operator == "sub":
            return left - right
        if node.operator == "mul":
            return left * right
        if node.operator == "div":
            return left / right.replace(0, pd.NA)
        raise AlphaDslError("unknown_operator", f"unsupported binary operator: {node.operator}")
    if isinstance(node, CallNode):
        return _evaluate_call(node, frame)
    raise AlphaDslError("unknown_node", f"unknown DSL node: {type(node).__name__}")


def _evaluate_call(node: CallNode, frame: pd.DataFrame) -> pd.Series:
    if node.function in {"ts_mean", "ts_std", "ts_zscore", "delta", "pct_change"}:
        values = pd.to_numeric(_evaluate_node(node.args[0], frame), errors="coerce")
        window = _window_arg(node.args[1])
        grouped = values.groupby(frame["instrument_id"], sort=False)
        if node.function == "ts_mean":
            return grouped.transform(lambda series: series.rolling(window=window, min_periods=window).mean())
        if node.function == "ts_std":
            return grouped.transform(lambda series: series.rolling(window=window, min_periods=window).std(ddof=0))
        if node.function == "ts_zscore":
            mean = grouped.transform(lambda series: series.rolling(window=window, min_periods=window).mean())
            std = grouped.transform(lambda series: series.rolling(window=window, min_periods=window).std(ddof=0))
            return (values - mean) / std.replace(0, pd.NA)
        if node.function == "delta":
            return grouped.transform(lambda series: series.diff(window))
        if node.function == "pct_change":
            return grouped.transform(lambda series: series.pct_change(periods=window))
    if node.function == "rank":
        values = pd.to_numeric(_evaluate_node(node.args[0], frame), errors="coerce")
        return values.groupby(frame["timestamp"], sort=False).rank(method="average", pct=True)
    if node.function == "zscore":
        values = pd.to_numeric(_evaluate_node(node.args[0], frame), errors="coerce")
        grouped = values.groupby(frame["timestamp"], sort=False)
        mean = grouped.transform("mean")
        std = grouped.transform(lambda series: series.std(ddof=0))
        return (values - mean) / std.replace(0, pd.NA)
    if node.function == "neutralize":
        values = pd.to_numeric(_evaluate_node(node.args[0], frame), errors="coerce")
        groups = _evaluate_node(node.args[1], frame)
        group_frame = pd.DataFrame({"timestamp": frame["timestamp"], "group": groups, "value": values})
        means = group_frame.groupby(["timestamp", "group"], sort=False)["value"].transform("mean")
        return values - means
    raise AlphaDslError("unknown_operator", f"operator is not implemented: {node.function}", node=node.function)


def _window_arg(node: DslNode) -> int:
    if not isinstance(node, NumberNode):
        raise AlphaDslError("invalid_window", "window arguments must be numeric literals")
    window = int(node.value)
    if window <= 0 or window != node.value:
        raise AlphaDslError("invalid_window", "window arguments must be positive integers")
    return window
