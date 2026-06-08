"""Asset-class-aware data adapters."""

from alphaops.data.adapters.base import AdapterHealth, AdapterMetadata, DataAdapter, FuturesDataAdapter
from alphaops.data.adapters.alpaca_market_data import AlpacaMarketDataAdapter
from alphaops.data.adapters.local_file import PrivateFileDataAdapter
from alphaops.data.adapters.massive_market_data import MassiveMarketDataAdapter
from alphaops.data.adapters.yfinance_equity import YFinanceEquityAdapter

__all__ = [
    "AdapterHealth",
    "AdapterMetadata",
    "AlpacaMarketDataAdapter",
    "DataAdapter",
    "FuturesDataAdapter",
    "MassiveMarketDataAdapter",
    "PrivateFileDataAdapter",
    "YFinanceEquityAdapter",
]
