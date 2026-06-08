"""Research-grade deterministic backtest engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass, BacktestContract, PositionDirection
from alphaops.quant.factors import evaluate_formula
from alphaops.quant.costs import (
    EquityCostModel,
    FuturesCostModel,
    FuturesTradingRules,
    estimate_equity_transaction_cost,
    estimate_futures_transaction_cost,
    futures_contract_count,
    futures_margin_requirement,
)
from alphaops.quant.metrics import drawdown_series
from alphaops.storage.duckdb import initialize_duckdb


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    alpha_id: str
    contract: BacktestContract
    weights: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: pd.DataFrame

    def persist(self, db_path: str | Path) -> int:
        return persist_backtest_result(db_path, self)


def run_backtest(
    contract: BacktestContract,
    factor_values: pd.DataFrame,
    market_bars: pd.DataFrame,
    *,
    run_id: str,
    initial_capital: float = 1_000_000.0,
    price_column: str = "adj_close",
) -> BacktestResult:
    """Run a deterministic long/short factor backtest."""

    contract.validate_asset_rules()
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    factors, bars, price_column = _prepare_inputs(factor_values, market_bars, price_column)
    allowed_assets = {asset.value for asset in contract.asset_classes}
    bars = bars[bars["asset_class"].isin(allowed_assets)].copy()
    factors = factors.merge(
        bars[["instrument_id", "timestamp", "asset_class", price_column]],
        on=["instrument_id", "timestamp"],
        how="inner",
    )
    if factors.empty:
        raise ValueError("no factor rows align with market bars and contract asset classes")
    alpha_id = str(factors["alpha_id"].iloc[0]) if "alpha_id" in factors.columns else run_id

    constraints = contract.portfolio_constraints
    equity_cost_model = EquityCostModel.from_dict(contract.equity_cost_model)
    futures_cost_model = FuturesCostModel.from_dict(contract.futures_cost_model)
    futures_rules = (
        FuturesTradingRules.from_dict(contract.futures_rules)
        if AssetClass.FUTURES in contract.asset_classes
        else None
    )
    if futures_rules:
        futures_rules.validate()

    returns = _forward_returns(bars, price_column)
    rebalance_dates = _rebalance_dates(sorted(factors["timestamp"].unique()), contract.rebalance_frequency)
    previous_weights: dict[str, float] = {}
    portfolio_value = initial_capital
    weight_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    curve_rows: list[dict[str, object]] = []

    for timestamp in rebalance_dates:
        timestamp = pd.Timestamp(timestamp)
        factor_slice = factors[factors["timestamp"] == timestamp].copy()
        if factor_slice.empty:
            continue
        target_weights = _construct_weights(factor_slice, constraints)
        period_returns = returns[returns["timestamp"] == timestamp].set_index("instrument_id")["forward_return"]
        gross_return = 0.0
        period_cost = 0.0
        turnover = 0.0

        for row in factor_slice.to_dict(orient="records"):
            instrument_id = row["instrument_id"]
            asset_class = str(row["asset_class"])
            target_weight = float(target_weights.get(instrument_id, 0.0))
            previous_weight = float(previous_weights.get(instrument_id, 0.0))
            trade_weight = target_weight - previous_weight
            turnover += abs(trade_weight)
            price = float(row[price_column])
            notional = trade_weight * portfolio_value
            cost = 0.0
            contract_count = None
            margin_requirement = None
            if asset_class in {AssetClass.EQUITY.value, AssetClass.ETF.value}:
                cost = estimate_equity_transaction_cost(notional, equity_cost_model)
            elif asset_class == AssetClass.FUTURES.value:
                if futures_rules is None:
                    raise ValueError("futures rules are required for futures rows")
                contract_count = futures_contract_count(notional, price, futures_rules)
                if futures_rules.position_direction == PositionDirection.LONG and target_weight < 0:
                    raise ValueError("futures rules allow only long positions")
                if futures_rules.position_direction == PositionDirection.SHORT and target_weight > 0:
                    raise ValueError("futures rules allow only short positions")
                margin_requirement = futures_margin_requirement(contract_count, futures_rules)
                cost = estimate_futures_transaction_cost(contract_count, futures_cost_model, futures_rules)
            period_cost += cost
            instrument_return = float(period_returns.get(instrument_id, 0.0))
            gross_return += target_weight * instrument_return
            weight_rows.append(
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "instrument_id": instrument_id,
                    "asset_class": asset_class,
                    "target_weight": target_weight,
                }
            )
            trade_rows.append(
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "instrument_id": instrument_id,
                    "asset_class": asset_class,
                    "trade_weight": trade_weight,
                    "notional": notional,
                    "cost": cost,
                    "contract_count": contract_count,
                    "margin_requirement": margin_requirement,
                }
            )

        cost_return = period_cost / portfolio_value
        period_return = gross_return - cost_return
        portfolio_value *= 1 + period_return
        curve_rows.append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "gross_return": gross_return,
                "period_return": period_return,
                "turnover": turnover,
                "cost": period_cost,
                "equity": portfolio_value,
            }
        )
        previous_weights = target_weights

    equity_curve = pd.DataFrame(curve_rows)
    if equity_curve.empty:
        raise ValueError("backtest produced no periods")
    equity_curve["drawdown"] = drawdown_series(equity_curve["period_return"])
    weights = pd.DataFrame(weight_rows)
    trades = pd.DataFrame(trade_rows)
    metrics = _compute_backtest_metrics(run_id, equity_curve, trades)
    return BacktestResult(
        run_id=run_id,
        alpha_id=alpha_id,
        contract=contract,
        weights=weights,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
    )


def load_backtest_market_bars(
    db_path: str | Path,
    *,
    asset_classes: list[AssetClass],
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    if not asset_classes:
        raise ValueError("Backtest Lab requires at least one asset class.")
    placeholders = ", ".join(["?"] * len(asset_classes))
    clauses = [f"asset_class IN ({placeholders})"]
    params: list[Any] = [asset.value for asset in asset_classes]
    if source_id:
        clauses.append("source_id = ?")
        params.append(source_id)
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT instrument_id, symbol, asset_class, timestamp, close, adj_close, volume, source_id, contract_id
            FROM market_bars
            WHERE {" AND ".join(clauses)}
            ORDER BY instrument_id, timestamp
            """,
            params,
        ).fetchdf()


def run_backtest_from_storage(
    db_path: str | Path,
    *,
    formula: str,
    contract: BacktestContract,
    run_id: str,
    alpha_id: str | None = None,
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    initial_capital: float = 1_000_000.0,
    persist: bool = True,
) -> dict[str, object]:
    bars = load_backtest_market_bars(
        db_path,
        asset_classes=contract.asset_classes,
        source_id=source_id,
        start=start,
        end=end,
    )
    if bars.empty:
        raise ValueError("No market_bars rows match the Backtest Lab selection.")
    factor_result = evaluate_formula(formula, bars, alpha_id=alpha_id or run_id)
    result = run_backtest(
        contract,
        factor_result.values,
        bars,
        run_id=run_id,
        initial_capital=initial_capital,
    )
    inserted = result.persist(initialize_duckdb(db_path)) if persist else 0
    return {"result": result, "factor_values": factor_result.values, "market_bars": bars, "inserted": inserted}


def _prepare_inputs(
    factor_values: pd.DataFrame,
    market_bars: pd.DataFrame,
    price_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    factor_required = {"instrument_id", "timestamp", "factor_value"}
    bar_required = {"instrument_id", "timestamp", "asset_class", price_column}
    if not bar_required.issubset(market_bars.columns) and price_column == "adj_close":
        price_column = "close"
        bar_required = {"instrument_id", "timestamp", "asset_class", price_column}
    missing_factor = factor_required.difference(factor_values.columns)
    missing_bars = bar_required.difference(market_bars.columns)
    if missing_factor:
        raise ValueError("factor_values missing columns: " + ", ".join(sorted(missing_factor)))
    if missing_bars:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing_bars)))
    factors = factor_values.copy()
    bars = market_bars.copy()
    factors["timestamp"] = pd.to_datetime(factors["timestamp"])
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    bars["asset_class"] = bars["asset_class"].astype(str)
    return factors, bars, price_column


def _forward_returns(bars: pd.DataFrame, price_column: str) -> pd.DataFrame:
    frame = bars.sort_values(["instrument_id", "timestamp"]).copy()
    frame["_price"] = pd.to_numeric(frame[price_column], errors="coerce")
    frame["forward_return"] = frame.groupby("instrument_id")["_price"].transform(
        lambda series: series.shift(-1) / series - 1
    )
    return frame.dropna(subset=["forward_return"])


def _rebalance_dates(timestamps: list[pd.Timestamp], frequency: str) -> list[pd.Timestamp]:
    normalized = frequency.lower()
    if normalized in {"1d", "daily", "d"}:
        step = 1
    elif normalized.endswith("d") and normalized[:-1].isdigit():
        step = int(normalized[:-1])
    else:
        raise ValueError(f"unsupported rebalance_frequency: {frequency}")
    return list(timestamps[::step])


def _construct_weights(factor_slice: pd.DataFrame, constraints: dict[str, object]) -> dict[str, float]:
    max_positions = int(constraints.get("max_positions", min(10, len(factor_slice))))
    max_weight = float(constraints.get("max_weight_per_instrument", 0.2))
    gross_exposure = float(constraints.get("max_gross_exposure", 1.0))
    long_short = bool(constraints.get("long_short", True))
    if max_positions <= 0:
        raise ValueError("max_positions must be positive")
    if max_weight <= 0 or gross_exposure <= 0:
        raise ValueError("portfolio weights and gross exposure must be positive")
    ranked = factor_slice.dropna(subset=["factor_value"]).sort_values("factor_value", ascending=False)
    if ranked.empty:
        return {}
    selected = ranked.head(max_positions)
    weights: dict[str, float] = {}
    if long_short and len(selected) >= 2:
        long_count = max(1, len(selected) // 2)
        short_count = len(selected) - long_count
        long_weight = min(max_weight, gross_exposure / 2 / long_count)
        short_weight = min(max_weight, gross_exposure / 2 / max(short_count, 1))
        for instrument_id in selected.head(long_count)["instrument_id"]:
            weights[str(instrument_id)] = long_weight
        for instrument_id in selected.tail(short_count)["instrument_id"]:
            weights[str(instrument_id)] = -short_weight
    else:
        weight = min(max_weight, gross_exposure / len(selected))
        for instrument_id in selected["instrument_id"]:
            weights[str(instrument_id)] = weight
    return weights


def _compute_backtest_metrics(run_id: str, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    period_returns = equity_curve["period_return"]
    metrics = {
        "cumulative_return": float(equity_curve["equity"].iloc[-1] / equity_curve["equity"].iloc[0] - 1),
        "max_drawdown": float(equity_curve["drawdown"].min()),
        "average_turnover": float(equity_curve["turnover"].mean()),
        "total_cost": float(trades["cost"].sum()),
        "period_count": float(len(equity_curve)),
        "mean_period_return": float(period_returns.mean()),
    }
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "metric_name": name,
                "metric_value": value,
                "created_at": created_at,
            }
            for name, value in metrics.items()
        ]
    )


def persist_backtest_result(db_path: str | Path, result: BacktestResult) -> int:
    created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    run_frame = pd.DataFrame(
        [
            {
                "run_id": result.run_id,
                "contract_id": result.contract.contract_id,
                "alpha_id": result.alpha_id,
                "initial_capital": _initial_capital(result.equity_curve),
                "final_equity": float(result.equity_curve["equity"].iloc[-1]),
                "created_at": created_at,
            }
        ]
    )
    contract_frame = pd.DataFrame(
        [
            {
                "contract_id": result.contract.contract_id,
                "asset_classes": json.dumps([asset.value for asset in result.contract.asset_classes]),
                "rebalance_frequency": result.contract.rebalance_frequency,
                "benchmark_id": result.contract.benchmark_id,
                "portfolio_constraints_json": json.dumps(result.contract.portfolio_constraints),
                "equity_cost_model_json": json.dumps(result.contract.equity_cost_model),
                "futures_cost_model_json": json.dumps(result.contract.futures_cost_model),
                "futures_rules_json": json.dumps(result.contract.futures_rules),
            }
        ]
    )
    metric_frame = pd.DataFrame(
        {
            "run_id": result.metrics["run_id"],
            "scope_id": result.contract.contract_id,
            "metric_name": result.metrics["metric_name"],
            "metric_value": result.metrics["metric_value"],
            "frequency": result.contract.rebalance_frequency,
            "created_at": result.metrics["created_at"],
        }
    )
    with duckdb.connect(str(db_path)) as conn:
        conn.register("contract_frame", contract_frame)
        conn.register("run_frame", run_frame)
        conn.register("weights_frame", result.weights)
        conn.register("trades_frame", result.trades)
        conn.register("curve_frame", result.equity_curve)
        conn.register("metric_frame", metric_frame)
        conn.execute("INSERT OR REPLACE INTO backtest_contracts SELECT * FROM contract_frame")
        conn.execute("INSERT OR REPLACE INTO backtest_runs SELECT * FROM run_frame")
        conn.execute("INSERT OR REPLACE INTO backtest_weights SELECT * FROM weights_frame")
        conn.execute("INSERT OR REPLACE INTO backtest_trades SELECT * FROM trades_frame")
        conn.execute("INSERT OR REPLACE INTO backtest_equity_curve SELECT * FROM curve_frame")
        conn.execute("INSERT OR REPLACE INTO metric_results SELECT * FROM metric_frame")
    return (
        len(contract_frame)
        + len(run_frame)
        + len(result.weights)
        + len(result.trades)
        + len(result.equity_curve)
        + len(metric_frame)
    )


def _initial_capital(equity_curve: pd.DataFrame) -> float:
    first = equity_curve.iloc[0]
    return float(first["equity"] / (1 + first["period_return"]))
