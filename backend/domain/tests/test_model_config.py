"""Configuration checks never read real credentials or contact a provider."""

import os
from pydantic import ValidationError
import pytest

from backend.domain.model_config import GeminiSettings, ModelConfigurationError


def test_explicit_environment_and_safe_serialization():
    settings = GeminiSettings.from_environment(environ={
        "GEMINI_API_KEY": "private_test_marker", "GEMINI_MODEL": "gemini-test-model",
    })
    assert settings.api_key.get_secret_value() == "private_test_marker"
    assert settings.model == "gemini-test-model"
    assert settings.timeout_ms == 30000 and settings.max_output_tokens == 2048
    assert "private_test_marker" not in repr(settings)
    assert "private_test_marker" not in settings.model_dump_json()
    assert "api_key" not in settings.model_dump()


@pytest.mark.parametrize("env,field", [
    ({}, "GEMINI_API_KEY"),
    ({"GEMINI_API_KEY": "fake-key"}, "GEMINI_MODEL"),
    ({"GEMINI_API_KEY": "", "GEMINI_MODEL": "gemini-test"}, "GEMINI_API_KEY"),
    ({"GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": ""}, "GEMINI_MODEL"),
])
def test_required_configuration(env, field):
    with pytest.raises(ModelConfigurationError, match=field):
        GeminiSettings.from_environment(environ=env)


@pytest.mark.parametrize("key", ["", " ", "test key", "key\n", "key\x00", "key\x7f", "kéy", "${OTHER_KEY}", "changeme", "replace_me", "your_gemini_api_key", "k" * 513])
def test_invalid_keys_are_never_echoed(key):
    with pytest.raises(ModelConfigurationError) as caught:
        GeminiSettings.from_environment(environ={"GEMINI_API_KEY": key, "GEMINI_MODEL": "gemini-test"})
    assert "input_value" not in str(caught.value)
    if key.strip() and len(key) > 10:
        assert key not in str(caught.value)


@pytest.mark.parametrize("model", ["", "model", "gemini-", "models/gemini-test", "https://host/gemini-test", "gemini-test?key=hidden", " gemini-test", "gemini-test\n", "gemini-" + "m" * 121])
def test_invalid_model_identifiers(model):
    with pytest.raises(ModelConfigurationError):
        GeminiSettings.from_environment(environ={"GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": model})


@pytest.mark.parametrize("name,value", [
    ("GEMINI_TIMEOUT_MS", "0"), ("GEMINI_TIMEOUT_MS", "999"), ("GEMINI_TIMEOUT_MS", "60001"),
    ("GEMINI_TIMEOUT_MS", "-1"), ("GEMINI_TIMEOUT_MS", "1000.0"), ("GEMINI_TIMEOUT_MS", "true"),
    ("GEMINI_TIMEOUT_MS", ""), ("GEMINI_TIMEOUT_MS", " 1000"), ("GEMINI_TIMEOUT_MS", "9" * 10000),
    ("GEMINI_MAX_OUTPUT_TOKENS", "127"), ("GEMINI_MAX_OUTPUT_TOKENS", "4097"),
    ("GEMINI_MAX_OUTPUT_TOKENS", "1e3"), ("GEMINI_MAX_OUTPUT_TOKENS", "2048.0"),
])
def test_invalid_environment_limits(name, value):
    with pytest.raises(ModelConfigurationError):
        GeminiSettings.from_environment(environ={
            "GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": "gemini-test", name: value,
        })


@pytest.mark.parametrize("timeout,tokens", [(1000, 128), (60000, 4096)])
def test_boundary_limits(timeout, tokens):
    settings = GeminiSettings.from_environment(environ={
        "GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": "gemini-test",
        "GEMINI_TIMEOUT_MS": str(timeout), "GEMINI_MAX_OUTPUT_TOKENS": str(tokens),
    })
    assert (settings.timeout_ms, settings.max_output_tokens) == (timeout, tokens)


@pytest.mark.parametrize("patch", [{"timeout_ms": True}, {"timeout_ms": "1000"}, {"max_output_tokens": 2048.0}, {"extra": "hidden"}])
def test_direct_settings_remain_strict(patch):
    with pytest.raises(ValidationError):
        GeminiSettings(api_key="fake-key", model="gemini-test", **patch)


def test_dotenv_precedence_no_interpolation_no_environment_mutation(tmp_path):
    env_file = tmp_path / "local.env"
    env_file.write_text('GEMINI_API_KEY="file_test_key"\nGEMINI_MODEL=gemini-file-model\nGEMINI_TIMEOUT_MS=1000\nPAYPAL_CLIENT_SECRET=unrelated\n', encoding="utf-8")
    before = dict(os.environ)
    settings = GeminiSettings.from_environment(env_file=env_file, environ={"GEMINI_API_KEY": "process_test_key"})
    assert settings.api_key.get_secret_value() == "process_test_key"
    assert settings.model == "gemini-file-model" and settings.timeout_ms == 1000
    assert dict(os.environ) == before
    assert "unrelated" not in repr(settings) + settings.model_dump_json()
    # An explicitly empty process key must not fall back to a file credential.
    with pytest.raises(ModelConfigurationError):
        GeminiSettings.from_environment(env_file=env_file, environ={"GEMINI_API_KEY": ""})
    env_file.write_text("GEMINI_API_KEY=${OTHER_KEY}\nGEMINI_MODEL=gemini-test\n", encoding="utf-8")
    with pytest.raises(ModelConfigurationError):
        GeminiSettings.from_environment(env_file=env_file, environ={"OTHER_KEY": "never_substituted"})


def test_unreadable_and_invalid_encoding_files(tmp_path):
    for path in (tmp_path / "missing.env", tmp_path):
        with pytest.raises(ModelConfigurationError, match="Cannot read"):
            GeminiSettings.from_environment(env_file=path, environ={})
    invalid = tmp_path / "invalid.env"
    invalid.write_bytes(b"\xff\xfe")
    with pytest.raises(ModelConfigurationError):
        GeminiSettings.from_environment(env_file=invalid, environ={})


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_explicit_thinking_level(level):
    settings = GeminiSettings.from_environment(environ={
        "GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": "gemini-test", "GEMINI_THINKING_LEVEL": level,
    })
    assert settings.thinking_level == level


@pytest.mark.parametrize("level", ["minimal", "LOW", "", "none", "private_marker"])
def test_invalid_thinking_level_is_not_echoed(level):
    with pytest.raises(ModelConfigurationError) as caught:
        GeminiSettings.from_environment(environ={
            "GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": "gemini-test", "GEMINI_THINKING_LEVEL": level,
        })
    assert "private_marker" not in str(caught.value)
