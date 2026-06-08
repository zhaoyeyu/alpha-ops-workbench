# AlphaOps Workbench Roadmap

AlphaOps Workbench is published as an alpha-stage research workbench. The roadmap is organized by product capability, not by promises that incomplete surfaces are finished.

## Product Direction

The target architecture remains:

```text
deterministic quant core
  + agent orchestration
  + interactive research UI
  + pluggable data sources
```

The primary research lines are short-horizon US equity alpha and futures alpha. Equity, ETF, and futures remain first-class asset classes. Crypto is currently an availability-check path, not a fully integrated research asset class.

## Implemented And Verifiable

### Product UI

- Chinese-default Streamlit browser workbench with English page content support.
- Home, Data Hub, Data Quality, Synthetic Index Lab, Alpha Factory, Backtest Lab, Alpha Registry, Risk Monitor, Agent Console, Report Center, Connector Admin, and Evaluation Dashboard.
- Pages call real services or persisted data instead of static placeholders.

### Data Platform

- Canonical market-bar contracts for Equity, ETF, and Futures.
- DuckDB schema, ingestion, lineage, adapter inventory, and data quality profiling.
- Massive authenticated US equity/ETF aggregate bars.
- yfinance Equity fallback.
- Alpaca stock bars/live-trade entrypoints.
- Local CSV/Parquet Private Data Ingestion Adapter.

### Quant And Research

- Universe construction, returns, metrics, factor engine, IC, and RankIC.
- Alpha DSL parser, AST validation, operator registry, and dependency tracking.
- Research backtests with configurable contracts, Equity/Futures cost models, constraints, and futures trading-rule fields.
- Synthetic index engine, Alpha Factory, Alpha Registry lifecycle, risk critic, reports, and evaluation cases.

### Local Use And Verification

- Python package and wheel.
- `alphaops configure`, `doctor`, `init`, `ui`, `api`, `smoke`, `massive-fetch`, `alpaca-stream`, and `alpaca-crypto-bars`.
- Windows setup/start scripts.
- Automated tests and GitHub Actions CI.

## Planned Capabilities

### Market Data Operations

- Persistent realtime event storage with reconnect, checkpoint, backfill, deduplication, and entitlement-aware error handling.
- Massive realtime WebSocket integration where the account subscription permits it.
- Provider capability discovery and clearer delayed/realtime status in Data Hub.
- Dataset versioning, adjustment policies, and reproducible snapshots.

### Futures Data

- Databento and/or IBKR adapters.
- Futures contract reference data, provider-backed session calendars, multipliers, margins, and tick metadata.
- Continuous-contract construction, configurable roll rules, and auditable roll maps.
- Historical and realtime futures quality checks.

### Quant Research Depth

- Broader Alpha DSL operator coverage and stronger formula diagnostics.
- Walk-forward evaluation, purged/embargoed validation, regime analysis, and richer benchmark attribution.
- Portfolio optimizer integrations and more detailed execution/cost simulations.
- Reproducible experiment manifests and comparison workflows.

### Agent And Evaluation

- User-configured OpenRouter model routing for planning, formula generation, workflow assistance, and report drafting.
- Stronger tool permissions, trace review, failure recovery, and evaluation suites.
- Human approval gates for high-impact workflow actions.

### Product And Distribution

- Richer charts, cross-page workflow state, saved research workspaces, and improved bilingual coverage.
- Authentication and multi-user project isolation.
- Structured logs, metrics, diagnostics, backup/restore, and migration tooling.
- Standalone Windows installer and signed release artifacts.

## Explicitly Not Complete

- Live trading, broker order execution, or portfolio management.
- Production SLA, security audit, regulatory compliance review, or investment-advice suitability.
- Fully integrated crypto research/backtesting.
- Provider-independent realtime coverage for all supported asset classes.
- Institutional validation of calculations, data licenses, or research conclusions.

## Completion Rules

A planned capability is complete only when:

- It performs a real product workflow rather than rendering a placeholder.
- It uses real or user-supplied data, not fake research results.
- It has deterministic verification or automated tests.
- Secrets remain outside source control and release artifacts.
- Documentation explains setup, limitations, and reproducibility.
