from alphaops.config import load_config


def test_openrouter_is_llm_gateway_not_data_source() -> None:
    config = load_config()
    assert config.llm_gateway.provider == "openrouter"
    assert config.llm_gateway.primary_key_env == "OPENROUTER_API_KEY_PRIMARY"
    assert config.llm_gateway.secondary_key_env == "OPENROUTER_API_KEY_SECONDARY"

