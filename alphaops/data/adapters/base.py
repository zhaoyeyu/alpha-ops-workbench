"""Base adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

import pandas as pd
from pydantic import BaseModel, ConfigDict

from alphaops.data.contracts import AssetClass, DataSourceKind


class AdapterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    asset_classes: list[AssetClass]
    source_kind: DataSourceKind
    permission_scope: str
    description: str


class AdapterHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    adapter: str
    message: str
    details: dict[str, str] = {}


class DataAdapter(ABC):
    metadata: AdapterMetadata

    @property
    def name(self) -> str:
        return self.metadata.name

    @abstractmethod
    def healthcheck(self) -> AdapterHealth:
        raise NotImplementedError

    @abstractmethod
    def load_bars(
        self,
        instruments: Iterable[str],
        start: str,
        end: str,
        frequency: str,
    ) -> pd.DataFrame:
        raise NotImplementedError


class FuturesDataAdapter(DataAdapter, ABC):
    """Independent futures adapter family for Databento/IBKR-style sources."""

    @abstractmethod
    def load_contracts(self, root_symbols: Iterable[str]) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def load_continuous_map(self, root_symbol: str, start: str, end: str) -> pd.DataFrame:
        raise NotImplementedError

