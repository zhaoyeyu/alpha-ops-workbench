from datetime import date, datetime, time

import pytest

from alphaops.data.contracts import (
    AlphaDslContract,
    AssetClass,
    BacktestContract,
    CanonicalMarketBar,
    ContinuousContractMap,
    FuturesContract,
    TradingSession,
    contract_names,
)


def test_required_contracts_include_multi_asset_and_research_objects() -> None:
    assert set(contract_names()) >= {
        "CanonicalMarketBar",
        "FuturesContract",
        "ContinuousContractMap",
        "TradingSession",
        "UniverseMember",
        "BacktestContract",
        "AlphaDslContract",
        "DataLineageRecord",
    }


def test_futures_market_bar_requires_contract_id() -> None:
    bar = CanonicalMarketBar(
        instrument_id="fut:micro_nq:202609",
        symbol="MNQU6",
        asset_class=AssetClass.FUTURES,
        timestamp=datetime(2026, 9, 1, 9, 30),
        frequency="1m",
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        volume=1000,
        currency="USD",
        exchange="CME",
        source_id="private_file",
        data_version="fixture",
        ingested_at=datetime(2026, 9, 1, 9, 31),
    )
    with pytest.raises(ValueError, match="contract_id"):
        bar.validate_ohlc_range()


def test_futures_contract_and_continuous_mapping_are_first_class() -> None:
    session = TradingSession(
        trading_session_id="cme_globex",
        exchange="CME",
        timezone="America/Chicago",
        day_session_start=time(8, 30),
        day_session_end=time(15, 15),
        night_session_start=time(17, 0),
        night_session_end=time(8, 30),
    )
    contract = FuturesContract(
        contract_id="cme_mnq_202609",
        root_symbol="MNQ",
        symbol="MNQU6",
        exchange="CME",
        contract_month="202609",
        multiplier=2.0,
        tick_size=0.25,
        currency="USD",
        initial_margin=2100,
        maintenance_margin=1900,
        trading_session_id=session.trading_session_id,
    )
    mapping = ContinuousContractMap(
        continuous_symbol="MNQ.c.0",
        root_symbol=contract.root_symbol,
        contract_id=contract.contract_id,
        roll_date=date(2026, 9, 10),
        roll_rule="volume_open_interest",
        weight=1.0,
    )
    assert contract.multiplier == 2.0
    assert mapping.continuous_symbol == "MNQ.c.0"


def test_research_grade_backtest_contract_requires_futures_rules() -> None:
    contract = BacktestContract(
        contract_id="bt_futures_short_alpha",
        asset_classes=[AssetClass.FUTURES],
        rebalance_frequency="intraday_30m",
        benchmark_id="MNQ.c.0",
        portfolio_constraints={"max_leverage": 2.0},
        futures_cost_model={"commission_per_contract": 0.35, "slippage_ticks": 1},
        futures_rules={
            "contract_multiplier": "from_contract",
            "margin": "from_contract",
            "leverage": "configured",
            "continuous_contract": "front_adjusted",
            "roll_logic": "volume_open_interest",
            "position_direction": ["long", "short"],
            "trading_sessions": "exchange_calendar",
        },
    )
    contract.validate_asset_rules()


def test_backtest_contract_rejects_missing_futures_rules() -> None:
    contract = BacktestContract(
        contract_id="bad",
        asset_classes=[AssetClass.FUTURES],
        rebalance_frequency="daily",
        benchmark_id="MNQ.c.0",
        portfolio_constraints={},
        futures_cost_model={},
        futures_rules={},
    )
    with pytest.raises(ValueError, match="futures backtests require futures_cost_model"):
        contract.validate_asset_rules()


def test_alpha_dsl_v01_contract_includes_required_integrations() -> None:
    dsl = AlphaDslContract(
        formula="rank(ts_mean(close, 20) / close)",
        dependencies=["close"],
        operator_names=["rank", "ts_mean", "divide"],
    )
    assert dsl.ast_version == "0.1"
    assert dsl.requires_ic_analysis
    assert dsl.requires_backtest_integration
    assert dsl.requires_registry_integration

