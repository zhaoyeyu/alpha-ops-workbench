from pathlib import Path

from alphaops import config


def test_installed_cli_can_load_env_from_current_working_directory(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("MASSIVE_API_KEY=local_test_key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAOPS_ENV_FILE", raising=False)

    config._load_local_environment()

    assert config.os.getenv("MASSIVE_API_KEY") == "local_test_key"


def test_explicit_env_file_is_supported(tmp_path, monkeypatch) -> None:
    env_path = Path(tmp_path) / "alphaops.local.env"
    env_path.write_text("MASSIVE_API_KEY=explicit_test_key\n", encoding="utf-8")
    monkeypatch.setenv("ALPHAOPS_ENV_FILE", str(env_path))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    config._load_local_environment()

    assert config.os.getenv("MASSIVE_API_KEY") == "explicit_test_key"
