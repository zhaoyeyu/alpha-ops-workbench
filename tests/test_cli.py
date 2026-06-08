from alphaops.cli import main
import pandas as pd


def test_doctor_reports_streamlit_as_primary_ui(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "primary_ui=streamlit" in output
    assert "massive_configured=" in output


def test_configure_writes_local_env_without_echoing_secret(tmp_path, capsys) -> None:
    env_path = tmp_path / ".env"
    secret = "local_massive_test_secret"

    assert main(["configure", "--env-file", str(env_path), "--massive-api-key", secret]) == 0

    output = capsys.readouterr().out
    assert secret not in output
    assert "MASSIVE_API_KEY=local_massive_test_secret" in env_path.read_text(encoding="utf-8")
    assert "secret_values_exposed=False" in output


def test_smoke_runs_real_product_paths(capsys) -> None:
    assert main(["smoke"]) == 0
    output = capsys.readouterr().out
    assert "smoke=passed" in output
    assert "quality_score=" in output
    assert "backtest_rows=" in output
    assert "synthetic_rows=" in output
    assert "evaluation_status=passed" in output


def test_api_launcher_invokes_uvicorn(monkeypatch) -> None:
    calls = []

    def fake_call(args):
        calls.append(args)
        return 0

    monkeypatch.setattr("alphaops.cli.subprocess.call", fake_call)
    assert main(["api", "--host", "127.0.0.1", "--port", "8765"]) == 0
    assert "uvicorn" in calls[0]
    assert "apps.api_fastapi.main:app" in calls[0]


def test_alpaca_stream_requires_credentials(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    assert main(["alpaca-stream", "--symbols", "NVDA", "--seconds", "1"]) == 1

    output = capsys.readouterr().out
    assert "ALPACA_API_KEY_ID" in output
    assert "ALPACA_API_SECRET_KEY" in output


def test_massive_fetch_requires_key(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    assert (
        main(
            [
                "massive-fetch",
                "--symbols",
                "NVDA",
                "--start",
                "2026-01-01",
                "--end",
                "2026-01-03",
                "--db-path",
                str(tmp_path / "alphaops.duckdb"),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "MASSIVE_API_KEY" in output


def test_alpaca_crypto_bars_cli_reports_rows(monkeypatch, capsys) -> None:
    def fake_load_alpaca_crypto_bars(*, symbol_list, start, end, frequency):
        assert symbol_list == ["BTC/USD"]
        assert frequency == "1d"
        return pd.DataFrame([{"symbol": "BTC/USD"}])

    monkeypatch.setattr("alphaops.cli._load_alpaca_crypto_bars", fake_load_alpaca_crypto_bars)

    assert main(["alpaca-crypto-bars", "--symbols", "BTC/USD", "--start", "2026-05-28", "--end", "2026-06-03"]) == 0

    output = capsys.readouterr().out
    assert "provider=alpaca_crypto" in output
    assert "rows=1" in output
