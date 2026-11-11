"""Terminal integration tests use explicit mock mode and synthetic policy."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from backend.domain import negotiate
from backend.domain.negotiation_fixtures import fixture_scenario


@pytest.mark.parametrize("shortfall,status", [(False, "agreed"), (True, "no_deal")])
def test_real_terminal_mock_mode_with_spawn_and_no_credentials(tmp_path, shortfall, status):
    path = tmp_path / "synthetic-scenario.json"
    path.write_text(fixture_scenario(30000, shortfall=shortfall).model_dump_json(), encoding="utf-8")
    import os
    environment = dict(os.environ)
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL"):
        environment.pop(key, None)
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "backend.domain.negotiate", "--mode", "mock", "--input", str(path)],
        cwd=Path(__file__).resolve().parents[3], env=environment,
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "mock" and payload["simulated"] is True
    assert payload["result"]["status"] == status and payload["result"]["quote"] is None
    assert 1 <= payload["result"]["turns"] <= 6
    for private_key in ("budget_cents", "minimum_total_cents", "stock_batches", "offer_options", "friday_navy"):
        assert private_key not in completed.stdout
    if not shortfall:
        assert payload["result"]["agreement"]["total_cents"] == 35400
    else:
        assert payload["result"]["agreement"] is None
        assert any(issue["shortfall_qty"] == 4 for issue in payload["result"]["issues"])


@pytest.mark.parametrize("payload", ["not json", "{}", '{"seller":{"policy":{"minimum_total_cents":"private_marker"}}}'])
def test_invalid_cli_input_never_echoes_private_values(tmp_path, capsys, payload):
    path = tmp_path / "input.json"
    path.write_text(payload, encoding="utf-8")
    assert negotiate.main(["--mode", "mock", "--input", str(path)]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "private_marker" not in captured.err


def test_mock_mode_never_loads_credentials_or_constructs_model(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_text(fixture_scenario(30000).model_dump_json(), encoding="utf-8")
    loader, client = MagicMock(), MagicMock()
    monkeypatch.setattr(negotiate.GeminiSettings, "from_environment", loader)
    monkeypatch.setattr(negotiate, "GeminiActionClient", client)
    # Exercise the CLI's construction path; the integration tests above execute
    # its actual engine and child processes.
    from backend.domain.negotiation import NegotiationResult
    monkeypatch.setattr(negotiate, "run_negotiation", lambda *args: NegotiationResult(status="no_deal", reason_code="turn_limit", turns=0))
    assert negotiate.main(["--mode", "mock", "--input", str(path)]) == 0
    loader.assert_not_called()
    client.assert_not_called()


def test_invalid_limits_missing_and_oversized_files(tmp_path, capsys):
    path = tmp_path / "input.json"
    assert negotiate.main(["--mode", "mock", "--input", str(path)]) == 1
    path.write_text(fixture_scenario(30000).model_dump_json(), encoding="utf-8")
    assert negotiate.main(["--mode", "mock", "--input", str(path), "--max-turns", "7"]) == 1
    path.write_bytes(b" " * (negotiate.MAX_INPUT_BYTES + 1))
    assert negotiate.main(["--mode", "mock", "--input", str(path)]) == 1
    assert not capsys.readouterr().out


@pytest.mark.parametrize("args", [[], ["--mode", "mock"], ["--input", "scenario.json"], ["--mode", "unknown", "--input", "scenario.json"]])
def test_mode_and_input_are_explicit(args):
    with pytest.raises(SystemExit) as caught:
        negotiate.main(args)
    assert caught.value.code == 2


def test_live_failure_stays_live_and_never_uses_fixture_agents(tmp_path, monkeypatch, capsys):
    from backend.domain.model_config import GeminiSettings
    from backend.domain.negotiation import NegotiationResult
    path = tmp_path / "private-scenario.json"
    path.write_text(fixture_scenario(30000).model_dump_json(), encoding="utf-8")
    settings = GeminiSettings(api_key="private_fake_key", model="gemini-test")
    loader = MagicMock(return_value=settings)
    factory, mock_agents = MagicMock(), MagicMock(side_effect=AssertionError("No mock fallback allowed"))
    monkeypatch.setattr(negotiate.GeminiSettings, "from_environment", loader)
    monkeypatch.setattr(negotiate, "GeminiActionClient", factory)
    monkeypatch.setattr(negotiate, "FixtureAgents", mock_agents)
    def failed(scenario, source, limits):
        assert source is factory.return_value
        return NegotiationResult(status="retryable_error", reason_code="model_error", turns=1)
    monkeypatch.setattr(negotiate, "run_negotiation", failed)
    selected_env = tmp_path / "explicit.env"
    assert negotiate.main(["--mode", "live", "--input", str(path), "--env-file", str(selected_env)]) == 1
    loader.assert_called_once_with(env_file=selected_env)
    factory.assert_called_once_with(settings)
    mock_agents.assert_not_called()
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["mode"] == "live" and output["simulated"] is False
    assert output["result"]["status"] == "retryable_error" and output["result"]["agreement"] is None
    assert "private_fake_key" not in captured.out + captured.err


def test_missing_live_configuration_stops_before_model_construction(tmp_path, monkeypatch, capsys):
    from backend.domain.model_config import ModelConfigurationError
    path = tmp_path / "private-scenario.json"
    path.write_text(fixture_scenario(30000).model_dump_json(), encoding="utf-8")
    loader = MagicMock(side_effect=ModelConfigurationError("GEMINI_API_KEY is required."))
    factory = MagicMock()
    monkeypatch.setattr(negotiate.GeminiSettings, "from_environment", loader)
    monkeypatch.setattr(negotiate, "GeminiActionClient", factory)
    assert negotiate.main(["--mode", "live", "--input", str(path)]) == 1
    factory.assert_not_called()
    captured = capsys.readouterr()
    assert not captured.out and "GEMINI_API_KEY" in captured.err
