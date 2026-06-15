# AlphaOps Workbench

[![CI](https://github.com/zhaoyeyu/alpha-ops-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/zhaoyeyu/alpha-ops-workbench/actions/workflows/ci.yml)

AlphaOps Workbench is a local-first quantitative research workbench for short-horizon US equity alpha and futures alpha. It combines a deterministic quant kernel, agent orchestration, Streamlit research UI, and pluggable data sources.

The browser UI is the primary interface. The command line supports installation, initialization, launch, API startup, and smoke checks.

AlphaOps Workbench is research software. It does not execute trades or provide investment advice.

## Current Status

- Streamlit workbench with 12 product pages.
- DuckDB storage, data contracts, lineage, and data quality checks.
- Massive US equity/ETF aggregate-bar ingestion using a user-provided API key.
- yfinance fallback, Alpaca stock adapter entrypoints, local CSV/Parquet private-data ingestion, and Alpaca crypto availability checks.
- Alpha DSL parsing/validation, factor calculation, IC/RankIC, research backtests, synthetic indexes, Alpha Registry lifecycle, risk review, reports, and evaluation cases.
- Local wheel installation, Windows scripts, `alphaops configure`, smoke tests, and GitHub Actions CI.

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned capabilities.

## Implemented Product Pages

- Home
- Data Hub
- Data Quality
- Synthetic Index Lab
- Alpha Factory
- Backtest Lab
- Alpha Registry
- Risk Monitor
- Agent Console
- Report Center
- Connector Admin
- Evaluation Dashboard

## Install Locally

From the project folder on Windows:

```powershell
python -m pip install -e ".[dev]"
alphaops configure --massive-api-key "your-key"
alphaops doctor
alphaops init
alphaops smoke
alphaops ui
```

Windows script equivalents:

```powershell
scripts/windows/install.ps1
scripts/windows/configure-local-secrets.ps1 -MassiveApiKey "your-key"
scripts/windows/init.ps1
scripts/windows/smoke.ps1
scripts/windows/start-ui.ps1
```

Optional API:

```powershell
alphaops api
```

## Install From Built Wheel

Build:

```powershell
python -m build
```

Install:

```powershell
python -m pip install --force-reinstall --no-deps dist/alphaops_workbench-0.1.0-py3-none-any.whl
alphaops smoke
alphaops ui
```

## Data And Secrets

OpenRouter is only an LLM gateway for agent planning, formula generation, report generation, and research workflows. It is not a market data source. Raw keys must stay in environment variables:

```text
OPENROUTER_API_KEY_PRIMARY
OPENROUTER_API_KEY_SECONDARY
```

Local CSV/Parquet is treated as a Private Data Ingestion Adapter. It enters the same Data Contract, Lineage, and Quality flow as public adapters.

## Market Data Ingestion

Use the Streamlit `???? / Data Hub` page:

- Public US equity/ETF: set `MASSIVE_API_KEY`, enter symbols such as `NVDA,MSFT,QQQ`, choose dates/frequency, then fetch through the Massive Market Data adapter.
- Public US equity fallback: yfinance remains available, but it may be rate-limited by its upstream source.
- Authenticated US equity: set `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`, choose Alpaca in Data Hub, then fetch bars through the Alpaca Market Data adapter.
- Realtime US equity trades: after setting Alpaca credentials, run `alphaops alpaca-stream --symbols NVDA,MSFT --seconds 15 --feed iex` to validate the live WebSocket connection.
- Crypto data check: `alphaops alpaca-crypto-bars --symbols BTC/USD --start 2026-05-28 --end 2026-06-03` validates Alpaca crypto market data access. Crypto is not yet part of the core equity/ETF/futures research contract.
- Private CSV/Parquet: upload or enter a local file path, choose `equity`, `etf`, or `futures`, then ingest through the Private Data Ingestion Adapter.
- Futures: provide private CSV/Parquet with `contract_id`; Databento/IBKR-style futures adapters are reserved for later provider integration.
- Sample workflow data: available in Data Hub for learning the UI only, not for research conclusions.

Massive uses `MASSIVE_API_KEY`. Alpaca feed defaults to `iex`; set `ALPACA_DATA_FEED=sip` only if your Alpaca subscription permits SIP access.

## Verification

```powershell
python -m pytest
python -m compileall alphaops apps
python -m build
alphaops smoke
```

Current validated baseline: 112 pytest tests pass.

## Documentation

- `docs/PROJECT_MANUAL.md`
- `docs/USER_GUIDE.md`
- `docs/DEMO_GUIDE.md`
- `docs/ROADMAP.md`
