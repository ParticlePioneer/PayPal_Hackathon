"""CLI success is tested with mocks; these checks are not live-model evidence."""

from unittest.mock import MagicMock

import pytest

from backend.domain import model_smoke
from backend.domain.contracts import AskAction
from backend.domain.model_client import ModelCallError
from backend.domain.openrouter_config import Settings as OpenRouterSettings
from backend.domain.model_config import ModelConfigurationError


@pytest.fixture
def configured(monkeypatch):
    config = OpenRouterSettings(api_key="private_key_marker", model="dots-studio/dots-3-note-preview:free")
    loader = MagicMock(return_value=config)
    factory = MagicMock()
    factory.return_value.generate_buyer.return_value = AskAction(type="ask", topic="delivery_options")
    factory.return_value.generate_seller.return_value = AskAction(type="ask", topic="revised_offer")
    monkeypatch.setattr(model_smoke.OpenRouterSettings, "from_environment", loader)
    monkeypatch.setattr(model_smoke, "OpenRouterActionClient", factory)
    return loader, factory


def test_check_configuration_is_explicitly_offline(configured, capsys):
    _, factory = configured
    assert model_smoke.main(["--check-config"]) == 0
    out = capsys.readouterr()
    assert "no request sent" in out.out and "Credentials were not verified" in out.out
    assert "private_key_marker" not in out.out + out.err
    factory.assert_not_called()


def test_default_smoke_one_buyer_call_no_private_output(configured, capsys):
    _, factory = configured
    assert model_smoke.main([]) == 0
    client = factory.return_value
    client.generate_buyer.assert_called_once()
    client.generate_seller.assert_not_called()
    out = capsys.readouterr()
    assert "action=ask" in out.out and "no negotiation, quote, or payment" in out.out
    for private in ("private_key_marker", "36000", "budget_cents", "minimum_total_cents"):
        assert private not in out.out + out.err


def test_missing_configuration_never_constructs_client(configured, capsys):
    loader, factory = configured
    loader.side_effect = ModelConfigurationError("OPENROUTER_API_KEY is required.")
    assert model_smoke.main([]) == 1
    factory.assert_not_called()
    out = capsys.readouterr()
    assert not out.out and "OPENROUTER_API_KEY" in out.err and "smoke passed" not in out.err


def test_model_failure_is_not_reported_as_success(configured, capsys):
    _, factory = configured
    factory.return_value.generate_buyer.side_effect = ModelCallError("rate_limited")
    assert model_smoke.main([]) == 1
    out = capsys.readouterr()
    assert not out.out and "quota" in out.err and "private_key_marker" not in out.err


def test_seller_requires_explicit_private_input(configured, capsys):
    _, factory = configured
    assert model_smoke.main(["--role", "seller"]) == 1
    assert "no policy is invented" in capsys.readouterr().err
    factory.assert_not_called()


def test_seller_supplied_input_is_forwarded_only_to_seller(configured, tmp_path, capsys):
    from backend.domain.contracts import SellerAgentInput, SellerPrivateInput, SellerPolicy
    from backend.domain.fixtures import buyer_fixture
    _, factory = configured
    path = tmp_path / "seller.json"
    # Synthetic CLI test input; no fixture policy is inferred.
    seller = SellerAgentInput(
        private=SellerPrivateInput(sku="shirts", stock_batches=(), policy=SellerPolicy(minimum_total_cents=12345)),
        shared=model_smoke.SharedNegotiationContext(requirements=buyer_fixture().requirements),
    )
    path.write_text(seller.model_dump_json(), encoding="utf-8")
    assert model_smoke.main(["--role", "seller", "--input", str(path)]) == 0
    factory.return_value.generate_seller.assert_called_once()
    factory.return_value.generate_buyer.assert_not_called()
    out = capsys.readouterr()
    assert "role=seller" in out.out
    assert "12345" not in out.out and "private_stock_marker" not in out.out


@pytest.mark.parametrize("payload", ["not json", "{}", '{"private":{"budget_cents":"private_marker"}}', "[1,2,3]"])
def test_invalid_input_file_is_sanitized(configured, tmp_path, capsys, payload):
    _, factory = configured
    path = tmp_path / "input.json"
    path.write_text(payload, encoding="utf-8")
    assert model_smoke.main(["--input", str(path)]) == 1
    out = capsys.readouterr()
    assert "private_marker" not in out.err and not out.out
    factory.assert_not_called()


def test_missing_and_oversized_input_files(configured, tmp_path, capsys):
    _, factory = configured
    missing = tmp_path / "input.json"
    assert model_smoke.main(["--input", str(missing)]) == 1
    missing.write_bytes(b" " * (model_smoke.MAX_INPUT_BYTES + 1))
    assert model_smoke.main(["--input", str(missing)]) == 1
    assert "private_key_marker" not in capsys.readouterr().err
    factory.assert_not_called()


def test_explicit_env_file_reaches_config_loader(configured, tmp_path):
    loader, _ = configured
    path = tmp_path / "local.env"
    assert model_smoke.main(["--env-file", str(path), "--check-config"]) == 0
    loader.assert_called_once_with(env_file=path)


def test_safe_provider_status_and_code_in_failure_output(configured, capsys):
    _, factory = configured
    factory.return_value.generate_buyer.side_effect = ModelCallError("request_rejected", provider_status=400)
    assert model_smoke.main([]) == 1
    out = capsys.readouterr()
    assert "code=request_rejected, http=400" in out.err
    assert "private_key_marker" not in out.err and not out.out
