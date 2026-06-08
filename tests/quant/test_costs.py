import pytest

from alphaops.data.contracts import PositionDirection
from alphaops.quant.costs import (
    EquityCostModel,
    FuturesCostModel,
    FuturesTradingRules,
    estimate_equity_transaction_cost,
    estimate_futures_transaction_cost,
    futures_contract_count,
    futures_margin_requirement,
    futures_notional,
)


def _rules() -> FuturesTradingRules:
    return FuturesTradingRules(
        contract_multiplier=2.0,
        margin=1200.0,
        leverage=5.0,
        continuous_contract="MNQ.C",
        roll_logic="volume_open_interest",
        position_direction=PositionDirection.LONG,
        trading_sessions=("CME_GLOBEX_DAY", "CME_GLOBEX_NIGHT"),
        tick_size=0.25,
        night_session=True,
    )


def test_equity_cost_model_uses_bps_and_minimum_commission() -> None:
    model = EquityCostModel(commission_bps=1.0, slippage_bps=2.0, min_commission=5.0)

    assert estimate_equity_transaction_cost(100_000, model) == pytest.approx(30.0)
    assert estimate_equity_transaction_cost(1_000, model) == pytest.approx(5.0)
    assert estimate_equity_transaction_cost(0, model) == 0.0


def test_futures_cost_model_uses_contract_terms() -> None:
    rules = _rules()
    model = FuturesCostModel(commission_per_contract=1.5, slippage_ticks=2.0, exchange_fee_per_contract=0.5)
    contracts = futures_contract_count(2_000.0, price=100.0, rules=rules)

    assert contracts == pytest.approx(10.0)
    assert futures_notional(contracts, price=100.0, rules=rules) == pytest.approx(2_000.0)
    assert futures_margin_requirement(contracts, rules) == pytest.approx(12_000.0)
    assert estimate_futures_transaction_cost(contracts, model, rules) == pytest.approx(30.0)


def test_futures_rules_require_research_grade_fields() -> None:
    with pytest.raises(ValueError):
        FuturesTradingRules.from_dict(
            {
                "contract_multiplier": 2,
                "margin": 1200,
                "leverage": 5,
                "continuous_contract": "MNQ.C",
                "roll_logic": "volume_open_interest",
                "position_direction": "long",
                "trading_sessions": [],
            }
        )

