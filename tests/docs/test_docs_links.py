from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docs_and_windows_scripts_cover_local_quant_user_workflow() -> None:
    docs = {
        "PROJECT_MANUAL.md": ROOT / "docs" / "PROJECT_MANUAL.md",
        "USER_GUIDE.md": ROOT / "docs" / "USER_GUIDE.md",
        "DEMO_GUIDE.md": ROOT / "docs" / "DEMO_GUIDE.md",
    }
    scripts = {
        "install.ps1": ROOT / "scripts" / "windows" / "install.ps1",
        "install-from-wheel.ps1": ROOT / "scripts" / "windows" / "install-from-wheel.ps1",
        "init.ps1": ROOT / "scripts" / "windows" / "init.ps1",
        "start-ui.ps1": ROOT / "scripts" / "windows" / "start-ui.ps1",
        "start-api.ps1": ROOT / "scripts" / "windows" / "start-api.ps1",
        "smoke.ps1": ROOT / "scripts" / "windows" / "smoke.ps1",
    }

    for path in [*docs.values(), *scripts.values()]:
        assert path.exists(), path

    combined_docs = "\n".join(path.read_text(encoding="utf-8") for path in docs.values())
    for required in [
        "Data Hub",
        "Data Quality",
        "Synthetic Index Lab",
        "Alpha Factory",
        "Backtest Lab",
        "Alpha Registry",
        "Risk Monitor",
        "Agent Console",
        "Report Center",
        "Connector Admin",
        "Evaluation Dashboard",
        "scripts/windows/install.ps1",
        "scripts/windows/install-from-wheel.ps1",
        "scripts/windows/start-ui.ps1",
        "scripts/windows/smoke.ps1",
        "OpenRouter is only the LLM gateway",
        "Private Data Ingestion Adapter",
    ]:
        assert required in combined_docs

    assert "alphaops smoke" in scripts["smoke.ps1"].read_text(encoding="utf-8")
    assert "alphaops ui" in scripts["start-ui.ps1"].read_text(encoding="utf-8")
