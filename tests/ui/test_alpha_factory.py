from datetime import datetime, timedelta

import duckdb
import pytest

from alphaops.data.contracts import AssetClass
from alphaops.lifecycle.factory import create_alpha_candidate_from_storage, load_factory_market_bars
from alphaops.storage.duckdb import initialize_duckdb


def _insert_market_bars(db_path):
    base = datetime(2026, 1, 1)
    prices = {
        "equity:a": ("A", [100.0, 110.0, 121.0]),
        "equity:b": ("B", [100.0, 120.0, 144.0]),
        "futures:mnq": ("MNQ", [100.0, 130.0, 169.0]),
    }
    rows = []
    for instrument_id, (symbol, series) in prices.items():
        asset_class = "futures" if instrument_id.startswith("futures") else "equity"
        for offset, price in enumerate(series):
            rows.append(
                (
                    instrument_id,
                    symbol,
                    asset_class,
                    base + timedelta(days=offset),
                    "1d",
                    price,
                    price,
                    price,
                    price,
                    price,
                    1000 + offset,
                    "USD",
                    "CME" if asset_class == "futures" else "NASDAQ",
                    "alpha_factory_fixture",
                    "fixture",
                    base,
                    "mnq_202603" if asset_class == "futures" else None,
                )
            )
    with duckdb.connect(str(db_path)) as conn:
        conn.executemany(
            "INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_alpha_factory_page_services_create_and_register_real_candidate(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _insert_market_bars(db_path)

    bars = load_factory_market_bars(db_path, asset_class=AssetClass.EQUITY, source_id="alpha_factory_fixture")
    result = create_alpha_candidate_from_storage(
        db_path,
        formula="rank(close)",
        asset_class=AssetClass.EQUITY,
        source_id="alpha_factory_fixture",
        register_for_review=True,
    )
    candidate = result["candidate"]
    payload = result["payload"]
    card = result["card"]

    assert len(bars) == 6
    assert candidate.state == "registry_review"
    assert candidate.dependencies == ("close",)
    assert candidate.operator_names == ("rank",)
    assert candidate.score == pytest.approx(payload["score"])
    assert card is not None
    assert card.alpha_id == candidate.candidate_id
    assert card.lifecycle_state.value == "registry_review"
    assert card.metrics["rank_ic_mean"] == pytest.approx(1.0)
