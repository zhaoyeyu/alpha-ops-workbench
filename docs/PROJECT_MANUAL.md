# AlphaOps Workbench Project Manual

AlphaOps Workbench is a local quantitative research workbench for short-horizon US equity alpha and futures alpha. The product architecture is:

- deterministic quant kernel
- agent orchestration layer
- interactive Streamlit research UI
- pluggable data sources

The main UI is the Streamlit browser workbench. The CLI is only a launcher and local control surface.

## Product Pages

- Home: product state overview and implemented scope.
- Data Hub: public adapter and Private Data Ingestion Adapter management.
- Data Quality: persisted quality reports, issue tables, score history, and instrument drilldown.
- Synthetic Index Lab: basket construction, weighting, benchmark comparison, costs, and methodology.
- Alpha Factory: Alpha DSL validation, factor preview, IC/RankIC scoring, and registry review submission.
- Backtest Lab: research-grade backtest contract, Equity/Futures costs, trades, weights, equity curve, and metrics.
- Alpha Registry: lifecycle states, metrics, risk flags, reports, and audited transitions.
- Risk Monitor: risk critic findings from backtest, quality, and lifecycle context.
- Agent Console: orchestrator workflow runs, tool traces, retries, approvals, and risk checkpoints.
- Report Center: deterministic Markdown/HTML report generation, inventory, and preview.
- Connector Admin: adapter health, credential slot status, permission scope, and secret redaction.
- Evaluation Dashboard: deterministic evaluation case execution and persisted results.

## Data Policy

OpenRouter is only the LLM gateway for planning, formula generation, report generation, and research workflow support. It is not a market data source. Raw API keys must be stored in environment variables only.

Local CSV/Parquet is the Private Data Ingestion Adapter. Imported datasets enter the same Data Contract, Lineage, and Quality flow as public data.

Massive Market Data is an authenticated public-online Equity/ETF adapter. It uses `MASSIVE_API_KEY`; raw credentials must remain in environment variables. Alpaca Market Data remains an optional authenticated public-online Equity adapter using `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, and optional `ALPACA_DATA_FEED`.

## Local Commands

```powershell
scripts/windows/install.ps1
scripts/windows/install-from-wheel.ps1
scripts/windows/init.ps1
scripts/windows/start-ui.ps1
scripts/windows/start-api.ps1
scripts/windows/smoke.ps1
```

Equivalent CLI:

```powershell
alphaops doctor
alphaops init
alphaops ui
alphaops api
alphaops smoke
```
