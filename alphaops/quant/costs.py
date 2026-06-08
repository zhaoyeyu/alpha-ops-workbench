"""Asset-class-specific trading cost models."""

from __future__ import annotations

from dataclasses import dataclass

from alphaops.data.contracts import PositionDirection


@dataclass(frozen=True)
class EquityCostModel:
    commission_bps: float = 1.0
    slippage_bps: float = 2.0
    min_commission: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, float] | None) -> "EquityCostModel":
        payload = payload or {}
        return cls(
            commission_bps=float(payload.get("commission_bps", cls.commission_bps)),
            slippage_bps=float(payload.get("slippage_bps", cls.slippage_bps)),
            min_commission=float(payload.get("min_commission", cls.min_commission)),
        )


@dataclass(frozen=True)
class FuturesCostModel:
    commission_per_contract: float = 1.5
    slippage_ticks: float = 1.0
    exchange_fee_per_contract: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, float] | None) -> "FuturesCostModel":
        payload = payload or {}
        return cls(
            commission_per_contract=float(payload.get("commission_per_contract", cls.commission_per_contract)),
            slippage_ticks=float(payload.get("slippage_ticks", cls.slippage_ticks)),
            exchange_fee_per_contract=float(payload.get("exchange_fee_per_contract", cls.exchange_fee_per_contract)),
        )


@dataclass(frozen=True)
class FuturesTradingRules:
    contract_multiplier: float
    margin: float
    leverage: float
    continuous_contract: str
    roll_logic: str
    position_direction: PositionDirection
    trading_sessions: tuple[str, ...]
    tick_size: float = 0.25
    night_session: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "FuturesTradingRules":
        if not payload:
            raise ValueError("futures_rules are required for futures backtests")
        sessions = payload.get("trading_sessions")
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("futures_rules.trading_sessions must be a non-empty list")
        direction = PositionDirection(str(payload.get("position_direction", PositionDirection.LONG.value)))
        return cls(
            contract_multiplier=float(payload["contract_multiplier"]),
            margin=float(payload["margin"]),
            leverage=float(payload["leverage"]),
            continuous_contract=str(payload["continuous_contract"]),
            roll_logic=str(payload["roll_logic"]),
            position_direction=direction,
            trading_sessions=tuple(str(session) for session in sessions),
            tick_size=float(payload.get("tick_size", 0.25)),
            night_session=bool(payload.get("night_session", False)),
        )

    def validate(self) -> None:
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive")
        if self.margin < 0:
            raise ValueError("margin must be non-negative")
        if self.leverage <= 0:
            raise ValueError("leverage must be positive")
        if not self.continuous_contract:
            raise ValueError("continuous_contract is required")
        if not self.roll_logic:
            raise ValueError("roll_logic is required")
        if not self.trading_sessions:
            raise ValueError("trading_sessions cannot be empty")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")


def estimate_equity_transaction_cost(notional: float, model: EquityCostModel) -> float:
    variable_cost = abs(notional) * (model.commission_bps + model.slippage_bps) / 10_000
    if abs(notional) == 0:
        return 0.0
    return max(variable_cost, model.min_commission)


def futures_contract_count(notional: float, price: float, rules: FuturesTradingRules) -> float:
    if price <= 0:
        raise ValueError("futures price must be positive")
    return notional / (price * rules.contract_multiplier)


def futures_notional(contract_count: float, price: float, rules: FuturesTradingRules) -> float:
    if price <= 0:
        raise ValueError("futures price must be positive")
    return contract_count * price * rules.contract_multiplier


def futures_margin_requirement(contract_count: float, rules: FuturesTradingRules) -> float:
    return abs(contract_count) * rules.margin


def estimate_futures_transaction_cost(
    contract_count: float,
    model: FuturesCostModel,
    rules: FuturesTradingRules,
) -> float:
    rules.validate()
    per_contract = (
        model.commission_per_contract
        + model.exchange_fee_per_contract
        + model.slippage_ticks * rules.tick_size * rules.contract_multiplier
    )
    return abs(contract_count) * per_contract
