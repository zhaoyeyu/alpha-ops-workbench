"""Dynamic universe construction for multi-asset research."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from alphaops.data.contracts import AssetClass, UniverseMember


class UniverseDefinition(BaseModel):
    """Rules for building a research universe from instruments and bars."""

    model_config = ConfigDict(extra="forbid")

    universe_id: str
    name: str
    asset_classes: list[AssetClass]
    min_average_volume: float = Field(default=0, ge=0)
    min_observations: int = Field(default=1, ge=1)
    top_n_by_liquidity: int | None = Field(default=None, ge=1)
    symbols: list[str] | None = None
    exchanges: list[str] | None = None
    root_symbols: list[str] | None = None

    @field_validator("asset_classes")
    @classmethod
    def require_asset_class(cls, value: list[AssetClass]) -> list[AssetClass]:
        if not value:
            raise ValueError("asset_classes cannot be empty")
        return value


def _normalize_date(value: date | str | pd.Timestamp) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def build_universe_members(
    instruments: pd.DataFrame,
    market_bars: pd.DataFrame,
    definition: UniverseDefinition,
    as_of_date: date | str | pd.Timestamp,
) -> list[UniverseMember]:
    """Build members from observed tradability and optional instrument filters."""

    required_instruments = {"instrument_id", "symbol", "asset_class", "exchange"}
    required_bars = {"instrument_id", "asset_class", "timestamp", "volume"}
    missing_instruments = required_instruments.difference(instruments.columns)
    missing_bars = required_bars.difference(market_bars.columns)
    if missing_instruments:
        raise ValueError("instruments missing columns: " + ", ".join(sorted(missing_instruments)))
    if missing_bars:
        raise ValueError("market_bars missing columns: " + ", ".join(sorted(missing_bars)))

    target_date = _normalize_date(as_of_date)
    asset_classes = {asset_class.value for asset_class in definition.asset_classes}

    instrument_frame = instruments.copy()
    bars_frame = market_bars.copy()
    instrument_frame["asset_class"] = instrument_frame["asset_class"].astype(str)
    bars_frame["asset_class"] = bars_frame["asset_class"].astype(str)
    bars_frame["timestamp"] = pd.to_datetime(bars_frame["timestamp"])

    instrument_frame = instrument_frame[instrument_frame["asset_class"].isin(asset_classes)]
    bars_frame = bars_frame[
        (bars_frame["asset_class"].isin(asset_classes))
        & (bars_frame["timestamp"].dt.date <= target_date)
    ]

    if definition.symbols:
        instrument_frame = instrument_frame[instrument_frame["symbol"].isin(definition.symbols)]
    if definition.exchanges:
        instrument_frame = instrument_frame[instrument_frame["exchange"].isin(definition.exchanges)]
    if definition.root_symbols and "root_symbol" in instrument_frame.columns:
        instrument_frame = instrument_frame[instrument_frame["root_symbol"].isin(definition.root_symbols)]

    liquidity = (
        bars_frame.groupby("instrument_id", as_index=False)
        .agg(
            average_volume=("volume", "mean"),
            observations=("volume", "size"),
            last_timestamp=("timestamp", "max"),
        )
    )
    candidates = instrument_frame.merge(liquidity, on="instrument_id", how="inner")
    candidates = candidates[
        (candidates["average_volume"] >= definition.min_average_volume)
        & (candidates["observations"] >= definition.min_observations)
    ]
    candidates = candidates.sort_values(
        ["average_volume", "observations", "instrument_id"],
        ascending=[False, False, True],
    )
    if definition.top_n_by_liquidity:
        candidates = candidates.head(definition.top_n_by_liquidity)

    members: list[UniverseMember] = []
    for row in candidates.to_dict(orient="records"):
        members.append(
            UniverseMember(
                universe_id=definition.universe_id,
                instrument_id=row["instrument_id"],
                asset_class=AssetClass(str(row["asset_class"])),
                effective_date=target_date,
                inclusion_reason=(
                    f"dynamic_liquidity_filter avg_volume={row['average_volume']:.4f} "
                    f"observations={int(row['observations'])}"
                ),
            )
        )
    return members


def persist_universe_members(
    db_path: str | Path,
    members: list[UniverseMember],
) -> int:
    """Persist a universe membership snapshot to DuckDB."""

    if not members:
        return 0
    rows = [
        {
            "universe_id": member.universe_id,
            "instrument_id": member.instrument_id,
            "asset_class": member.asset_class.value,
            "effective_date": member.effective_date,
            "end_date": member.end_date,
            "inclusion_reason": member.inclusion_reason,
        }
        for member in members
    ]
    frame = pd.DataFrame(rows)
    with duckdb.connect(str(db_path)) as conn:
        conn.register("members_frame", frame)
        conn.execute(
            """
            INSERT OR REPLACE INTO universe_members
            SELECT universe_id, instrument_id, asset_class, effective_date, end_date, inclusion_reason
            FROM members_frame
            """
        )
    return len(rows)

