"""Multi-asset data contracts for AlphaOps Workbench."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    FUTURES = "futures"


class DataSourceKind(StrEnum):
    PUBLIC_ONLINE = "public_online"
    PRIVATE_FILE = "private_file"
    DATABASE = "database"


class BarFrequency(StrEnum):
    DAILY = "1d"
    MINUTE = "1m"
    HOUR = "1h"


class PositionDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class CanonicalMarketBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    symbol: str
    asset_class: AssetClass
    timestamp: datetime
    frequency: BarFrequency
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    currency: str
    exchange: str
    source_id: str
    data_version: str
    ingested_at: datetime
    adj_close: float | None = Field(default=None, gt=0)
    contract_id: str | None = None

    @field_validator("high")
    @classmethod
    def high_positive(cls, value: float) -> float:
        return value

    def validate_ohlc_range(self) -> None:
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must be at least open/low/close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must be at most open/high/close")
        if self.asset_class == AssetClass.FUTURES and not self.contract_id:
            raise ValueError("futures market bars require contract_id")


class FuturesContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: str
    root_symbol: str
    symbol: str
    exchange: str
    contract_month: str
    multiplier: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    currency: str
    first_trade_date: date | None = None
    last_trade_date: date | None = None
    initial_margin: float | None = Field(default=None, ge=0)
    maintenance_margin: float | None = Field(default=None, ge=0)
    trading_session_id: str | None = None


class ContinuousContractMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    continuous_symbol: str
    root_symbol: str
    contract_id: str
    roll_date: date
    roll_rule: str
    weight: float = Field(ge=0, le=1)


class TradingSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trading_session_id: str
    exchange: str
    timezone: str
    day_session_start: time
    day_session_end: time
    night_session_start: time | None = None
    night_session_end: time | None = None


class UniverseMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    universe_id: str
    instrument_id: str
    asset_class: AssetClass
    effective_date: date
    end_date: date | None = None
    inclusion_reason: str


class BacktestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: str
    asset_classes: list[AssetClass]
    rebalance_frequency: str
    benchmark_id: str
    portfolio_constraints: dict[str, Any]
    equity_cost_model: dict[str, Any] | None = None
    futures_cost_model: dict[str, Any] | None = None
    futures_rules: dict[str, Any] | None = None

    @field_validator("asset_classes")
    @classmethod
    def asset_classes_not_empty(cls, value: list[AssetClass]) -> list[AssetClass]:
        if not value:
            raise ValueError("asset_classes cannot be empty")
        return value

    def validate_asset_rules(self) -> None:
        if AssetClass.EQUITY in self.asset_classes and not self.equity_cost_model:
            raise ValueError("equity backtests require equity_cost_model")
        if AssetClass.FUTURES in self.asset_classes:
            if not self.futures_cost_model:
                raise ValueError("futures backtests require futures_cost_model")
            required = {
                "contract_multiplier",
                "margin",
                "leverage",
                "continuous_contract",
                "roll_logic",
                "position_direction",
                "trading_sessions",
            }
            missing = required.difference((self.futures_rules or {}).keys())
            if missing:
                raise ValueError("futures_rules missing: " + ", ".join(sorted(missing)))


class AlphaDslContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: str
    ast_version: str = "0.1"
    dependencies: list[str]
    operator_names: list[str]
    requires_ic_analysis: bool = True
    requires_backtest_integration: bool = True
    requires_registry_integration: bool = True


class DataLineageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lineage_id: str
    asset_class: AssetClass | None = None
    source_kind: DataSourceKind
    source_id: str
    adapter_name: str
    schema_name: str
    schema_hash: str
    input_hash: str
    output_hash: str
    run_id: str
    created_at: datetime
    permission_scope: str


MARKET_BAR_COLUMNS = tuple(CanonicalMarketBar.model_fields.keys())


def validate_market_bars_frame(frame: pd.DataFrame) -> list[str]:
    missing = [column for column in MARKET_BAR_COLUMNS if column not in frame.columns]
    if missing:
        return missing
    for row in frame.to_dict(orient="records"):
        bar = CanonicalMarketBar(**row)
        bar.validate_ohlc_range()
    return []


def contract_names() -> list[str]:
    return [
        "CanonicalMarketBar",
        "FuturesContract",
        "ContinuousContractMap",
        "TradingSession",
        "UniverseMember",
        "BacktestContract",
        "AlphaDslContract",
        "DataLineageRecord",
    ]

