from datetime import datetime

import pytest

from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.storage.duckdb import initialize_duckdb
from alphaops.tools.registry import default_tool_registry
from alphaops.tools.schema import ToolCallError, ToolCategory


def _bars() -> list[dict[str, object]]:
    rows = []
    prices = {
        "eq:a": [100.0, 110.0, 121.0],
        "eq:b": [100.0, 120.0, 144.0],
    }
    for instrument_id, series in prices.items():
        for day, price in enumerate(series, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "symbol": instrument_id.split(":")[1].upper(),
                    "asset_class": "equity",
                    "timestamp": datetime(2026, 1, day),
                    "frequency": "1d",
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "adj_close": price,
                    "volume": 1000,
                    "currency": "USD",
                    "exchange": "NASDAQ",
                    "source_id": "fixture",
                    "data_version": "test",
                    "ingested_at": datetime(2026, 1, day),
                    "contract_id": None,
                }
            )
    return rows


def _factor_values() -> list[dict[str, object]]:
    return [
        {"alpha_id": "alpha_tool", "instrument_id": "eq:a", "timestamp": datetime(2026, 1, 1), "factor_value": 1.0},
        {"alpha_id": "alpha_tool", "instrument_id": "eq:b", "timestamp": datetime(2026, 1, 1), "factor_value": 2.0},
        {"alpha_id": "alpha_tool", "instrument_id": "eq:a", "timestamp": datetime(2026, 1, 2), "factor_value": 1.0},
        {"alpha_id": "alpha_tool", "instrument_id": "eq:b", "timestamp": datetime(2026, 1, 2), "factor_value": 2.0},
    ]


def test_tool_registry_exposes_typed_capabilities() -> None:
    registry = default_tool_registry()
    definitions = {definition.name: definition for definition in registry.definitions()}

    assert definitions["quant.backtest.run"].category == ToolCategory.QUANT
    assert definitions["llm.openrouter.request"].category == ToolCategory.LLM_GATEWAY
    assert definitions["llm.openrouter.request"].deterministic is False
    assert all(definition.name for definition in definitions.values())


def test_tools_call_real_deterministic_services() -> None:
    registry = default_tool_registry()

    quality = registry.call("data_quality.profile_market_bars", {"dataset_id": "bars", "market_bars": _bars()})
    factor = registry.call(
        "quant.factor.evaluate",
        {"alpha_id": "alpha_tool", "formula": "rank(close)", "market_bars": _bars()},
    )
    evaluation = registry.call(
        "evaluation.ic_run",
        {"alpha_id": "alpha_tool", "factor_values": _factor_values(), "market_bars": _bars()},
    )

    assert quality.audit["service"] == "alphaops.data.quality.profile_market_bars"
    assert factor.output["registry_payload"]["formula"] == "rank(close)"
    assert "rank_ic_mean" in evaluation.output["summary"]
    assert factor.audit["agent_direct_metric_calculation"] is False


def test_backtest_tool_runs_deterministic_backtest() -> None:
    registry = default_tool_registry()
    result = registry.call(
        "quant.backtest.run",
        {
            "run_id": "tool_backtest",
            "initial_capital": 100_000,
            "contract": {
                "contract_id": "tool_contract",
                "asset_classes": ["equity"],
                "rebalance_frequency": "1d",
                "benchmark_id": "eq:b",
                "portfolio_constraints": {
                    "max_positions": 2,
                    "max_weight_per_instrument": 0.5,
                    "max_gross_exposure": 1.0,
                    "long_short": False,
                },
                "equity_cost_model": {"commission_bps": 1, "slippage_bps": 1},
            },
            "factor_values": _factor_values(),
            "market_bars": _bars(),
        },
    )

    assert result.output["run_id"] == "tool_backtest"
    assert result.output["trades_rows"] > 0
    assert "cumulative_return" in result.output["metrics"]


def test_registry_report_and_risk_tools_use_persisted_registry(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    alpha_registry = AlphaRegistry(db_path)
    alpha_registry.register_for_review(
        {
            "alpha_id": "alpha_tool_registry",
            "formula": "rank(close)",
            "ast_version": "0.1",
            "metrics": {"rank_ic_mean": 0.05},
        }
    )
    registry = default_tool_registry()

    transitioned = registry.call(
        "registry.transition",
        {
            "db_path": str(db_path),
            "alpha_id": "alpha_tool_registry",
            "target_state": "approved",
            "actor": "test",
            "reason": "tool_test",
            "report_link": "reports/alpha_tool_registry.md",
        },
    )
    risk = registry.call("risk.review_alpha", {"metrics": {"rank_ic_mean": -0.01, "max_drawdown": -0.3}})
    report = registry.call(
        "report.render_alpha_card",
        {"db_path": str(db_path), "alpha_id": "alpha_tool_registry"},
    )

    assert transitioned.output["lifecycle_state"] == "approved"
    assert risk.output["flags"][0]["code"] == "negative_rank_ic"
    assert "# Alpha alpha_tool_registry" in report.output["markdown"]


def test_openrouter_tool_is_llm_gateway_not_financial_data_source() -> None:
    registry = default_tool_registry()
    result = registry.call(
        "llm.openrouter.request",
        {
            "requested_use": "research_workflow",
            "request": {
                "workflow": "planning",
                "model": "openrouter/auto",
                "messages": [{"role": "user", "content": "Plan an alpha research workflow"}],
            },
        },
    )

    assert result.output["gateway"] == "openrouter"
    assert result.output["is_financial_data_source"] is False
    with pytest.raises(ToolCallError):
        registry.call(
            "llm.openrouter.request",
            {
                "requested_use": "market_data",
                "request": {
                    "workflow": "planning",
                    "model": "openrouter/auto",
                    "messages": [{"role": "user", "content": "Fetch prices"}],
                },
            },
        )
