"""Connector administration services with safe credential status reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alphaops.config import load_config
from alphaops.data.adapters import AlpacaMarketDataAdapter, MassiveMarketDataAdapter, PrivateFileDataAdapter, YFinanceEquityAdapter
from alphaops.data.contracts import AssetClass


CONNECTOR_CREDENTIAL_SLOTS = (
    {"connector": "openrouter", "env_var": "OPENROUTER_API_KEY_PRIMARY", "purpose": "LLM gateway primary key"},
    {"connector": "openrouter", "env_var": "OPENROUTER_API_KEY_SECONDARY", "purpose": "LLM gateway secondary key"},
    {"connector": "alpaca_market_data", "env_var": "ALPACA_API_KEY_ID", "purpose": "Alpaca market data API key id"},
    {"connector": "alpaca_market_data", "env_var": "ALPACA_API_SECRET_KEY", "purpose": "Alpaca market data API secret key"},
    {"connector": "massive_market_data", "env_var": "MASSIVE_API_KEY", "purpose": "Massive market data API key"},
    {"connector": "databento_futures", "env_var": "DATABENTO_API_KEY", "purpose": "future futures data adapter slot"},
    {"connector": "ibkr", "env_var": "IBKR_GATEWAY_URL", "purpose": "future broker/data gateway slot"},
)


def connector_health_inventory(private_file_path: str | Path | None = None) -> list[dict[str, Any]]:
    adapters = [YFinanceEquityAdapter(), MassiveMarketDataAdapter(), AlpacaMarketDataAdapter()]
    if private_file_path:
        adapters.append(PrivateFileDataAdapter(private_file_path, asset_class=AssetClass.EQUITY))
    rows = []
    for adapter in adapters:
        health = adapter.healthcheck()
        rows.append(
            {
                "connector": adapter.name,
                "source_kind": adapter.metadata.source_kind.value,
                "asset_classes": [asset.value for asset in adapter.metadata.asset_classes],
                "permission_scope": adapter.metadata.permission_scope,
                "description": adapter.metadata.description,
                "ok": health.ok,
                "message": health.message,
                "details": health.details,
            }
        )
    return rows


def credential_slot_status() -> list[dict[str, Any]]:
    config = load_config()
    env = {
        "OPENROUTER_API_KEY_PRIMARY": config.llm_gateway.has_primary_key,
        "OPENROUTER_API_KEY_SECONDARY": config.llm_gateway.has_secondary_key,
    }
    rows = []
    for slot in CONNECTOR_CREDENTIAL_SLOTS:
        env_var = slot["env_var"]
        configured = bool(env.get(env_var, False))
        if env_var not in env:
            configured = _env_present(env_var)
        rows.append(
            {
                "connector": slot["connector"],
                "env_var": env_var,
                "purpose": slot["purpose"],
                "configured": configured,
                "display_value": "<set>" if configured else "<missing>",
                "raw_secret_exposed": False,
            }
        )
    return rows


def connector_admin_snapshot(private_file_path: str | Path | None = None) -> dict[str, Any]:
    return {
        "connectors": connector_health_inventory(private_file_path),
        "credential_slots": credential_slot_status(),
        "secret_policy": "Only environment variable names and presence flags are displayed; raw secret values are never returned.",
    }


def _env_present(name: str) -> bool:
    import os

    return bool(os.getenv(name))
