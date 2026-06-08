from datetime import datetime

import pandas as pd
import pytest

from alphaops.quant.alpha_dsl import AlphaDslError
from alphaops.quant.factors import evaluate_formula


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "instrument_id": "eq:a",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 1),
                "open": 9.0,
                "close": 10.0,
                "adj_close": 10.0,
                "volume": 1000,
            },
            {
                "instrument_id": "eq:b",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 1),
                "open": 20.0,
                "close": 20.0,
                "adj_close": 20.0,
                "volume": 2000,
            },
            {
                "instrument_id": "eq:a",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 2),
                "open": 10.0,
                "close": 12.0,
                "adj_close": 12.0,
                "volume": 3000,
            },
            {
                "instrument_id": "eq:b",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 2),
                "open": 20.0,
                "close": 18.0,
                "adj_close": 18.0,
                "volume": 4000,
            },
            {
                "instrument_id": "fut:mnq",
                "asset_class": "futures",
                "timestamp": datetime(2026, 1, 2),
                "open": 100.0,
                "close": 105.0,
                "adj_close": 105.0,
                "volume": 5000,
            },
        ]
    )


def test_factor_engine_computes_cross_sectional_rank() -> None:
    result = evaluate_formula("rank(close)", _bars(), alpha_id="alpha_rank_close")
    day_two = result.values[result.values["timestamp"] == pd.Timestamp("2026-01-02")]

    factor_values = dict(zip(day_two["instrument_id"], day_two["factor_value"], strict=True))
    assert factor_values == pytest.approx({"eq:a": 1 / 3, "eq:b": 2 / 3, "fut:mnq": 1.0})
    assert result.for_ic_analysis().columns.tolist() == [
        "alpha_id",
        "instrument_id",
        "timestamp",
        "factor_value",
    ]
    assert result.for_backtest().equals(result.for_ic_analysis())


def test_factor_engine_computes_time_series_and_binary_formula() -> None:
    result = evaluate_formula(
        "ts_mean(close, 2) - ts_mean(open, 2)",
        _bars(),
        alpha_id="alpha_ts_spread",
    )
    eq_a_day_two = result.values[
        (result.values["instrument_id"] == "eq:a")
        & (result.values["timestamp"] == pd.Timestamp("2026-01-02"))
    ]["factor_value"].iloc[0]

    assert eq_a_day_two == pytest.approx(1.5)


def test_factor_engine_neutralization_hook_subtracts_group_mean() -> None:
    result = evaluate_formula(
        "neutralize(close, asset_class)",
        _bars(),
        alpha_id="alpha_neutralized_close",
    )
    day_two = result.values[result.values["timestamp"] == pd.Timestamp("2026-01-02")]
    factor_values = dict(zip(day_two["instrument_id"], day_two["factor_value"], strict=True))

    assert factor_values["eq:a"] == pytest.approx(-3.0)
    assert factor_values["eq:b"] == pytest.approx(3.0)
    assert factor_values["fut:mnq"] == pytest.approx(0.0)


def test_factor_engine_registry_payload_contains_dsl_contract_metadata() -> None:
    result = evaluate_formula("pct_change(adj_close, 1)", _bars(), alpha_id="alpha_pct_change")
    payload = result.for_alpha_registry()

    assert payload == {
        "alpha_id": "alpha_pct_change",
        "formula": "pct_change(adj_close, 1)",
        "ast_version": "0.1",
        "dependencies": ["adj_close"],
        "operator_names": ["pct_change"],
    }


def test_factor_engine_invalid_formula_fails_safely() -> None:
    with pytest.raises(AlphaDslError) as error:
        evaluate_formula("rank(missing_column)", _bars(), alpha_id="bad_alpha")

    assert error.value.as_dict()["code"] == "unknown_field"
