import duckdb

from alphaops.storage.duckdb import initialize_duckdb, list_tables


def test_duckdb_initializes_full_product_schema(tmp_path) -> None:
    db_path = tmp_path / "alphaops.duckdb"
    initialize_duckdb(db_path)
    tables = set(list_tables(db_path))
    assert tables >= {
        "instruments",
        "futures_contracts",
        "trading_sessions",
        "continuous_contract_map",
        "market_bars",
        "universe_members",
        "return_series",
        "metric_results",
        "backtest_contracts",
        "data_lineage",
        "quality_reports",
        "quality_issues",
        "alpha_registry",
        "agent_runs",
        "reports",
        "evaluation_cases",
    }


def test_schema_accepts_equity_etf_and_futures_rows(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["eq:nvda", "NVDA", "equity", "NASDAQ", "USD", None, "NVIDIA"],
        )
        conn.execute(
            "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["etf:qqq", "QQQ", "etf", "NASDAQ", "USD", None, "Invesco QQQ"],
        )
        conn.execute(
            "INSERT INTO futures_contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "cme_mnq_202609",
                "MNQ",
                "MNQU6",
                "CME",
                "202609",
                2.0,
                0.25,
                "USD",
                None,
                None,
                2100,
                1900,
                "cme_globex",
            ],
        )
        assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 2
        assert conn.execute("SELECT multiplier FROM futures_contracts").fetchone()[0] == 2.0
