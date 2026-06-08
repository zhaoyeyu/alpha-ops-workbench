import json

import pandas as pd

from alphaops.data.adapters.admin import connector_admin_snapshot, connector_health_inventory, credential_slot_status


def test_connector_admin_reports_health_and_never_exposes_raw_secret(monkeypatch, tmp_path) -> None:
    private_file = tmp_path / "private.csv"
    pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "trade_date": "2026-01-01",
                "open_px": 100,
                "high_px": 101,
                "low_px": 99,
                "close_px": 100.5,
                "vol": 1000,
            }
        ]
    ).to_csv(private_file, index=False)
    monkeypatch.setenv("OPENROUTER_API_KEY_PRIMARY", "secret_value_that_must_not_render")

    snapshot = connector_admin_snapshot(private_file)
    serialized = json.dumps(snapshot)

    assert {item["connector"] for item in snapshot["connectors"]} == {
        "yfinance_equity",
        "massive_market_data",
        "alpaca_market_data",
        "private_csv_parquet",
    }
    assert all("permission_scope" in item for item in snapshot["connectors"])
    assert any(item["env_var"] == "OPENROUTER_API_KEY_PRIMARY" and item["configured"] for item in snapshot["credential_slots"])
    assert "secret_value_that_must_not_render" not in serialized
    assert all(item["display_value"] in {"<set>", "<missing>"} for item in snapshot["credential_slots"])
    assert all(item["raw_secret_exposed"] is False for item in snapshot["credential_slots"])


def test_connector_admin_individual_services_are_real() -> None:
    health = connector_health_inventory()
    credentials = credential_slot_status()

    assert health[0]["connector"] == "yfinance_equity"
    assert "public_online" in {health[0]["source_kind"]}
    assert {item["connector"] for item in credentials} >= {
        "openrouter",
        "massive_market_data",
        "alpaca_market_data",
        "databento_futures",
        "ibkr",
    }
