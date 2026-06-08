# GitHub Release Checklist

## Must Pass Before Push

- `python -m pytest`
- `python -m compileall alphaops apps`
- `python -m build`
- `python -m pip install --force-reinstall --no-deps dist/alphaops_workbench-0.1.0-py3-none-any.whl`
- `alphaops smoke`
- Run a secret scan for OpenRouter-style keys and configured key values. Do not include known leaked key fragments as literal text in repository files.

## Do Not Commit

- `.env`
- `.taskstate-vault/`
- `._quarantine/`
- `storage/warehouse/`
- `storage/raw/`
- `storage/lake/`
- `storage/experiments/`
- `dist/`
- `release_dist/`
- `build/`
- `*.egg-info/`

## Repository And Release Decisions

- Public source repository: `zhaoyeyu/alpha-ops-workbench`.
- Whether to publish `dist/` files as GitHub Release assets or keep only source in Git.
- Preferred license owner name if different from `AlphaOps Workbench Contributors`.
- GitHub Actions currently runs on every push and pull request.
- Whether to create a first release tag such as `v0.1.0`.

## First Release Artifacts

- Source repository.
- Wheel: `dist/alphaops_workbench-0.1.0-py3-none-any.whl`.
- Source distribution: `dist/alphaops_workbench-0.1.0.tar.gz`.
- Local Windows release bundle under `release_dist/`.

## Secret Policy

OpenRouter keys and any future Databento/IBKR credentials must be provided through environment variables only. Raw keys must never be committed, documented, printed, or displayed in UI.
