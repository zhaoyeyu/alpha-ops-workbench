# Full Product Demo Fixture

This directory documents the full product smoke path used by `tests/smoke/test_full_product_smoke.py`.

The smoke path creates temporary local data at runtime instead of committing market data files. It exercises:

- local package CLI smoke
- FastAPI status
- Streamlit page route files
- Agent Console persisted traces
- Connector Admin secret-safe snapshot
- deterministic evaluation cases

Run:

```powershell
python -m pytest tests/smoke/test_full_product_smoke.py
```
