# AlphaOps Workbench Demo Guide

The demo path proves the product is more than a static dashboard.

## Quick Demo

```powershell
cd <your AlphaOps Workbench checkout>
scripts/windows/install.ps1
scripts/windows/init.ps1
scripts/windows/smoke.ps1
scripts/windows/start-ui.ps1
```

## What the Smoke Demo Exercises

- DuckDB schema initialization.
- Stored market bars for Equity, ETF, and Futures.
- Data Quality profiling and persisted report creation.
- Alpha DSL formula validation and Alpha Factory candidate scoring.
- Alpha Registry review persistence.
- Backtest Lab with Equity/Futures cost and trading rules.
- Synthetic Index Lab index levels, constituent weights, and benchmark metrics.
- Risk Monitor findings and persisted risk flags.
- Report Center deterministic report rendering and file registration.
- Evaluation Dashboard deterministic evaluation case execution.

## Verified Full Product Smoke

The pytest smoke covers the CLI smoke, API status route, Streamlit page route files, Agent Console persisted trace service, and Connector Admin secret-safe status:

```powershell
python -m pytest tests/smoke/test_full_product_smoke.py
```

## UI Demo Route

After starting the UI, open these pages:

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

Every page is expected to use real product services or persisted data. Static placeholder pages are not accepted as completion.
