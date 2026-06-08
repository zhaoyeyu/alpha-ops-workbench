"""Local launcher/control CLI.

The CLI is not the product UI. The product UI is the Streamlit browser workbench.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
from importlib.resources import files
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from tempfile import TemporaryDirectory

import duckdb
from dotenv import set_key

from alphaops.data.contracts import AssetClass, BacktestContract
from alphaops.data.adapters.alpaca_market_data import ALPACA_KEY_ENV, ALPACA_SECRET_ENV, AlpacaMarketDataAdapter
from alphaops.data.adapters.massive_market_data import MASSIVE_API_KEY_ENV
from alphaops.data.hub import ingest_public_market_massive
from alphaops.data.quality import profile_stored_market_bars
from alphaops.evals.cases import run_evaluation_cases
from alphaops.lifecycle.factory import create_alpha_candidate_from_storage
from alphaops.quant.backtest import run_backtest_from_storage
from alphaops.reports.renderer import render_report, save_report_document
from alphaops.risk.critic import RiskThresholds, run_risk_review_from_storage
from alphaops.config import load_config
from alphaops.storage.duckdb import initialize_duckdb, list_tables
from alphaops.synthetic.engine import SyntheticIndexConfig, WeightingScheme, run_synthetic_index_from_storage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alphaops")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("init")
    configure = subparsers.add_parser("configure")
    configure.add_argument("--env-file", default=".env", help="Local environment file path. Defaults to .env in the current directory.")
    configure.add_argument("--massive-api-key")
    configure.add_argument("--alpaca-api-key-id")
    configure.add_argument("--alpaca-api-secret-key")
    configure.add_argument("--openrouter-primary-key")
    configure.add_argument("--openrouter-secondary-key")

    ui = subparsers.add_parser("ui")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int)
    api = subparsers.add_parser("api")
    api.add_argument("--host", default=None)
    api.add_argument("--port", type=int)
    subparsers.add_parser("smoke")
    alpaca_stream = subparsers.add_parser("alpaca-stream")
    alpaca_stream.add_argument("--symbols", required=True, help="Comma-separated US equity symbols, for example NVDA,MSFT.")
    alpaca_stream.add_argument("--seconds", type=int, default=15, help="How long to listen for live trades.")
    alpaca_stream.add_argument("--feed", default="iex", help="Alpaca data feed: iex, sip, delayed_sip, or another allowed feed.")
    alpaca_crypto = subparsers.add_parser("alpaca-crypto-bars")
    alpaca_crypto.add_argument("--symbols", default="BTC/USD", help="Comma-separated crypto symbols, for example BTC/USD,ETH/USD.")
    alpaca_crypto.add_argument("--start", required=True)
    alpaca_crypto.add_argument("--end", required=True)
    alpaca_crypto.add_argument("--frequency", default="1d", choices=["1m", "1h", "1d"])
    massive_fetch = subparsers.add_parser("massive-fetch")
    massive_fetch.add_argument("--symbols", required=True, help="Comma-separated US stock or ETF symbols, for example NVDA,QQQ.")
    massive_fetch.add_argument("--start", required=True, help="Start date, for example 2026-05-28.")
    massive_fetch.add_argument("--end", required=True, help="End date, for example 2026-06-03.")
    massive_fetch.add_argument("--frequency", default="1d", choices=["1m", "1h", "1d", "1wk", "1mo"])
    massive_fetch.add_argument("--asset-class", default=AssetClass.EQUITY.value, choices=[AssetClass.EQUITY.value, AssetClass.ETF.value])
    massive_fetch.add_argument("--db-path", default=None)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "init":
        return _init()
    if args.command == "configure":
        return _configure(
            env_file=args.env_file,
            massive_api_key=args.massive_api_key,
            alpaca_api_key_id=args.alpaca_api_key_id,
            alpaca_api_secret_key=args.alpaca_api_secret_key,
            openrouter_primary_key=args.openrouter_primary_key,
            openrouter_secondary_key=args.openrouter_secondary_key,
        )
    if args.command == "ui":
        return _ui(host=args.host, port=args.port)
    if args.command == "api":
        return _api(host=args.host, port=args.port)
    if args.command == "smoke":
        return _smoke()
    if args.command == "alpaca-stream":
        return _alpaca_stream(symbols=args.symbols, seconds=args.seconds, feed=args.feed)
    if args.command == "alpaca-crypto-bars":
        return _alpaca_crypto_bars(
            symbols=args.symbols,
            start=args.start,
            end=args.end,
            frequency=args.frequency,
        )
    if args.command == "massive-fetch":
        return _massive_fetch(
            symbols=args.symbols,
            start=args.start,
            end=args.end,
            frequency=args.frequency,
            asset_class=AssetClass(args.asset_class),
            db_path=args.db_path,
        )
    return 2


def _doctor() -> int:
    config = load_config()
    print(f"env={config.app.env}")
    print(f"duckdb_path={config.paths.duckdb_path}")
    print("primary_ui=streamlit")
    print(f"openrouter_primary_configured={config.llm_gateway.has_primary_key}")
    print(f"openrouter_secondary_configured={config.llm_gateway.has_secondary_key}")
    print(f"massive_configured={bool(os.getenv('MASSIVE_API_KEY'))}")
    return 0


def _init() -> int:
    db_path = initialize_duckdb()
    print(f"initialized={db_path}")
    print("tables=" + ",".join(sorted(list_tables(db_path))))
    return 0


def _configure(
    *,
    env_file: str,
    massive_api_key: str | None,
    alpaca_api_key_id: str | None,
    alpaca_api_secret_key: str | None,
    openrouter_primary_key: str | None,
    openrouter_secondary_key: str | None,
) -> int:
    target = Path(env_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    values = {
        "MASSIVE_API_KEY": massive_api_key,
        "ALPACA_API_KEY_ID": alpaca_api_key_id,
        "ALPACA_API_SECRET_KEY": alpaca_api_secret_key,
        "OPENROUTER_API_KEY_PRIMARY": openrouter_primary_key,
        "OPENROUTER_API_KEY_SECONDARY": openrouter_secondary_key,
    }
    configured = []
    for name, value in values.items():
        if value:
            set_key(str(target), name, value, quote_mode="never")
            configured.append(name)
    if not configured:
        print("error=no key values provided")
        return 1
    print(f"env_file={target}")
    print("configured=" + ",".join(configured))
    print("secret_values_exposed=False")
    return 0


def _ui(*, host: str, port: int | None) -> int:
    config = load_config()
    app_path = files("apps.dashboard_streamlit").joinpath("Home.py")
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            host,
            "--server.port",
            str(port or config.app.streamlit_port),
        ]
    )


def _api(*, host: str | None, port: int | None) -> int:
    config = load_config()
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api_fastapi.main:app",
            "--host",
            host or config.app.api_host,
            "--port",
            str(port or config.app.api_port),
        ]
    )


def _smoke() -> int:
    with TemporaryDirectory(prefix="alphaops_smoke_") as temp_dir:
        db_path = initialize_duckdb(f"{temp_dir}/alphaops.duckdb")
        _seed_smoke_market_bars(db_path)
        quality = profile_stored_market_bars(db_path, asset_class=AssetClass.EQUITY, source_id="smoke_fixture")
        candidate_payload = create_alpha_candidate_from_storage(
            db_path,
            formula="rank(close)",
            asset_class=AssetClass.EQUITY,
            source_id="smoke_fixture",
            register_for_review=True,
        )
        contract = BacktestContract(
            contract_id="smoke_contract",
            asset_classes=[AssetClass.EQUITY, AssetClass.FUTURES],
            rebalance_frequency="1d",
            benchmark_id="equity:b",
            portfolio_constraints={
                "max_positions": 2,
                "max_weight_per_instrument": 0.3,
                "max_gross_exposure": 0.6,
                "long_short": False,
            },
            equity_cost_model={"commission_bps": 1.0, "slippage_bps": 1.0, "min_commission": 0.0},
            futures_cost_model={"commission_per_contract": 1.5, "slippage_ticks": 1.0, "exchange_fee_per_contract": 0.5},
            futures_rules={
                "contract_multiplier": 2.0,
                "margin": 1200.0,
                "leverage": 5.0,
                "continuous_contract": "MNQ.C",
                "roll_logic": "volume_open_interest",
                "position_direction": "long",
                "trading_sessions": ["CME_GLOBEX_DAY", "CME_GLOBEX_NIGHT"],
                "tick_size": 0.25,
                "night_session": True,
            },
        )
        backtest = run_backtest_from_storage(
            db_path,
            formula="rank(close)",
            contract=contract,
            run_id="smoke_backtest",
            source_id="smoke_fixture",
            initial_capital=100_000,
        )
        synthetic = run_synthetic_index_from_storage(
            db_path,
            config=SyntheticIndexConfig(
                index_id="smoke_synthetic",
                name="Smoke Synthetic",
                weighting_scheme=WeightingScheme.LIQUIDITY_WEIGHT,
                benchmark_id="etf:qqq",
            ),
            instrument_ids=["equity:a", "equity:b", "futures:mnq"],
        )
        risk = run_risk_review_from_storage(
            db_path,
            run_id="smoke_backtest",
            alpha_id=candidate_payload["candidate"].candidate_id,
            thresholds=RiskThresholds(),
            persist_flags=True,
        )
        report = render_report(
            report_id="smoke_report",
            title="AlphaOps Smoke Report",
            sections={
                "Quality": {"quality_score": quality.quality_score},
                "Backtest": dict(zip(backtest["result"].metrics["metric_name"], backtest["result"].metrics["metric_value"], strict=True)),
                "Synthetic": synthetic.methodology,
                "Risk": risk["review"].summary(),
            },
            source_links=["smoke:market_bars", "smoke:backtest", "smoke:synthetic", "smoke:risk"],
            reproducibility={"command": "alphaops smoke"},
        )
        save_report_document(db_path, report, output_dir=f"{temp_dir}/reports", report_type="smoke", source_run_id="smoke")
        evals = run_evaluation_cases(db_path, case_ids=["schema_tool_registry"])
        print("smoke=passed")
        print(f"db_path={db_path}")
        print(f"quality_score={quality.quality_score}")
        print(f"alpha_id={candidate_payload['candidate'].candidate_id}")
        print(f"backtest_rows={len(backtest['result'].equity_curve)}")
        print(f"synthetic_rows={len(synthetic.levels)}")
        print(f"risk_findings={len(risk['review'].findings)}")
        print(f"evaluation_status={evals[0].status}")
    return 0


def _alpaca_stream(*, symbols: str, seconds: int, feed: str) -> int:
    symbol_list = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    if not symbol_list:
        print("error=at least one symbol is required")
        return 1
    if seconds <= 0:
        print("error=seconds must be greater than 0")
        return 1

    adapter = AlpacaMarketDataAdapter(feed=feed)
    health = adapter.healthcheck()
    if not health.ok:
        print(f"error={health.message}")
        print(f"set {ALPACA_KEY_ENV} and {ALPACA_SECRET_ENV} in your PowerShell environment")
        return 1

    trade_count = 0

    async def on_trade(trade) -> None:
        nonlocal trade_count
        trade_count += 1
        symbol = getattr(trade, "symbol", "")
        price = getattr(trade, "price", "")
        size = getattr(trade, "size", "")
        timestamp = getattr(trade, "timestamp", "")
        print(f"trade symbol={symbol} price={price} size={size} timestamp={timestamp}")

    try:
        stream = adapter.subscribe_trades(symbol_list, on_trade)
    except Exception as exc:
        print(f"error={exc}")
        return 1

    def run_stream() -> None:
        try:
            stream.run()
        except Exception as exc:  # pragma: no cover - depends on remote websocket behavior.
            print(f"stream_error={exc}")

    thread = threading.Thread(target=run_stream, daemon=True)
    thread.start()
    try:
        time.sleep(seconds)
    finally:
        _stop_alpaca_stream(stream)
        thread.join(timeout=5)
    print(f"symbols={','.join(symbol_list)}")
    print(f"feed={feed}")
    print(f"trades={trade_count}")
    return 0


def _stop_alpaca_stream(stream) -> None:
    if hasattr(stream, "stop"):
        result = stream.stop()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
        return
    if hasattr(stream, "stop_ws"):
        result = stream.stop_ws()
        if asyncio.iscoroutine(result):
            asyncio.run(result)


def _massive_fetch(
    *,
    symbols: str,
    start: str,
    end: str,
    frequency: str,
    asset_class: AssetClass,
    db_path: str | None,
) -> int:
    symbol_list = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    if not symbol_list:
        print("error=at least one symbol is required")
        return 1

    config = load_config()
    target_db = db_path or str(config.paths.duckdb_path)
    try:
        result = ingest_public_market_massive(
            db_path=target_db,
            symbols=symbol_list,
            start=start,
            end=end,
            frequency=frequency,
            asset_class=asset_class,
        )
    except Exception as exc:
        print(f"error={exc}")
        if MASSIVE_API_KEY_ENV in str(exc):
            print(f"set {MASSIVE_API_KEY_ENV} in your PowerShell environment")
        return 1

    print("provider=massive")
    print(f"asset_class={asset_class.value}")
    print(f"symbols={','.join(symbol_list)}")
    print(f"frequency={frequency}")
    print(f"rows={result['rows']}")
    print(f"lineage_id={result['lineage_id']}")
    print(f"db_path={target_db}")
    return 0


def _alpaca_crypto_bars(*, symbols: str, start: str, end: str, frequency: str) -> int:
    symbol_list = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    if not symbol_list:
        print("error=at least one crypto symbol is required")
        return 1
    try:
        frame = _load_alpaca_crypto_bars(symbol_list=symbol_list, start=start, end=end, frequency=frequency)
    except Exception as exc:
        print(f"error={exc}")
        return 1
    print("provider=alpaca_crypto")
    print(f"symbols={','.join(symbol_list)}")
    print(f"frequency={frequency}")
    print(f"rows={len(frame)}")
    return 0


def _load_alpaca_crypto_bars(*, symbol_list: list[str], start: str, end: str, frequency: str):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    mapping = {"1m": TimeFrame.Minute, "1h": TimeFrame.Hour, "1d": TimeFrame.Day}
    client = CryptoHistoricalDataClient()
    request = CryptoBarsRequest(
        symbol_or_symbols=symbol_list,
        timeframe=mapping[frequency],
        start=pd_timestamp_utc(start),
        end=pd_timestamp_utc(end),
    )
    return client.get_crypto_bars(request).df


def pd_timestamp_utc(value: str):
    import pandas as pd

    return pd.Timestamp(value, tz="UTC").to_pydatetime()


def _seed_smoke_market_bars(db_path) -> None:
    base = datetime(2026, 1, 1)
    prices = {
        "equity:a": ("A", "equity", [100.0, 110.0, 121.0], 1000.0),
        "equity:b": ("B", "equity", [100.0, 120.0, 132.0], 3000.0),
        "futures:mnq": ("MNQ", "futures", [100.0, 130.0, 143.0], 6000.0),
        "etf:qqq": ("QQQ", "etf", [100.0, 115.0, 126.5], 9000.0),
    }
    rows = []
    for instrument_id, (symbol, asset_class, series, volume) in prices.items():
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
                    volume,
                    "USD",
                    "CME" if asset_class == "futures" else "NASDAQ",
                    "smoke_fixture",
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


if __name__ == "__main__":
    raise SystemExit(main())
