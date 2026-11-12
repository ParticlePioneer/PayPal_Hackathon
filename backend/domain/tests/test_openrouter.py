import json
import time

import httpx
import pytest

from backend.domain.agent_process import call_agent_bounded
from backend.domain.model_client import ModelCallError
from backend.domain.tests.test_model_client import buyer_input, seller_input
from backend.domain.openrouter_client import OpenRouterActionClient, parse_completion
from backend.domain.openrouter_config import ConfigurationError, Settings
from backend.domain.evaluate import evaluate_with_conversation


def completion(content='{"action":{"type":"ask","topic":"delivery_options"}}', finish="stop"):
    return {"model": "test-model", "provider": "test-provider", "choices": [
        {"finish_reason": finish, "message": {"content": content}}]}


@pytest.mark.parametrize("role", ["buyer", "seller"])
def test_role_input_and_actual_http_format(monkeypatch, tmp_path, role):
    requests = []
    real_client = httpx.Client
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion(), headers={"set-cookie": "secret", "x-test": "fake-key"})
    monkeypatch.setattr("backend.domain.openrouter_client.httpx.Client", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    path = tmp_path / "trace.jsonl"
    client = OpenRouterActionClient(Settings("fake-key"), response_trace=path)
    client.trace_case = "case"
    assert getattr(client, f"generate_{role}")(buyer_input() if role == "buyer" else seller_input()).type == "ask"
    req = requests[0]
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer fake-key"
    sent = json.loads(req.content)
    assert sent["model"].endswith(":free") and sent["provider"]["require_parameters"] is True
    assert sent["response_format"] == {"type": "json_object"}
    data = json.loads(sent["messages"][1]["content"])
    assert data["role"] == role
    if role == "buyer":
        assert "private_stock_marker" not in json.dumps(data) and "minimum_total_cents" not in json.dumps(data)
    else:
        assert "budget_cents" not in json.dumps(data)
    trace = json.loads(path.read_text())
    assert trace["case"] == "case" and trace["role"] == role and trace["status_code"] == 200
    assert "fake-key" not in path.read_text() and trace["headers"]["set-cookie"] == "[REDACTED]"


@pytest.mark.parametrize("status,code", [(400,"request_rejected"), (401,"credentials_rejected"),
    (403,"credentials_rejected"), (404,"model_unavailable"), (429,"rate_limited"), (500,"provider_unavailable")])
def test_http_errors_are_sanitized(monkeypatch, status, code):
    real_client = httpx.Client
    monkeypatch.setattr("backend.domain.openrouter_client.httpx.Client", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error": "fake-key"})), **kw))
    with pytest.raises(ModelCallError) as error:
        OpenRouterActionClient(Settings("fake-key")).generate_buyer(buyer_input())
    assert error.value.code == code and "fake-key" not in str(error.value)


@pytest.mark.parametrize("body,code", [
    (completion("bad"), "invalid_response"),
    (completion('{"action":{"type":"ask","type":"decline"}}'), "invalid_response"),
    (completion('{"action":{"type":"ask","topic":"delivery_options","extra":1}}'), "invalid_response"),
    (completion(finish="length"), "incomplete_response"),
    (completion(finish="content_filter"), "blocked_response"),
    ({"error": {"code": 502, "message": "upstream failed"}}, "provider_unavailable"),
    ({"choices": []}, "invalid_response"),
    (completion(None), "empty_response"),
])
def test_reject_bad_completions(body, code):
    with pytest.raises(ModelCallError) as error:
        parse_completion(body)
    assert error.value.code == code


def test_network_timeout(monkeypatch):
    real_client = httpx.Client
    def handle(_):
        raise httpx.ReadTimeout("private")
    monkeypatch.setattr("backend.domain.openrouter_client.httpx.Client", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(ModelCallError) as error:
        OpenRouterActionClient(Settings("fake-key")).generate_buyer(buyer_input())
    assert error.value.code == "timeout"


def test_settings_explicit_free_only_and_env_precedence(tmp_path):
    path = tmp_path / "env"
    path.write_text("OPENROUTER_API_KEY=file-key\nOPENROUTER_MODEL=example/model:free\n")
    settings = Settings.from_environment(env_file=path, environ={"OPENROUTER_API_KEY": "process-key"})
    assert settings.api_key == "process-key" and settings.model == "example/model:free"
    assert "process-key" not in repr(settings)
    with pytest.raises(ConfigurationError):
        Settings.from_environment(env_file=path, environ={"OPENROUTER_MODEL": "example/model"})
    with pytest.raises(ConfigurationError):
        Settings.from_environment(env_file=path, environ={"OPENROUTER_API_KEY": ""})


class SlowSource:
    def generate_buyer(self, data):
        time.sleep(5)


def test_parent_timeout_stops_worker():
    with pytest.raises(ModelCallError) as error:
        call_agent_bounded(SlowSource(), "buyer", buyer_input(), 300)
    assert error.value.code == "timeout"


def test_conversation_includes_every_attempt_and_stops_on_decline(monkeypatch):
    from backend.domain import negotiation
    from backend.domain.contracts import AskAction, DeclineAction
    from backend.domain.evaluate import scenarios
    actions = iter([AskAction(type="ask", topic="delivery_options"),
                    DeclineAction(type="decline", reason_code="terms_unacceptable")])
    original = lambda *args: next(actions)
    monkeypatch.setattr(negotiation, "call_agent_bounded", original)
    _, _, scenario = scenarios()[0]
    result = evaluate_with_conversation(None, scenario, False, limits=negotiation.NegotiationLimits())
    assert negotiation.call_agent_bounded is original
    assert result["status"] == "no_deal" and result["matches_expected"] is True
    assert [x["role"] for x in result["attempts"]] == ["buyer", "seller"]
    assert [x["actor"] for x in result["conversation"]] == ["buyer", "seller"]
    assert all(x["recorded_in_conversation"] for x in result["attempts"])


def test_invalid_reference_is_logged_but_not_recorded(monkeypatch):
    from backend.domain import negotiation
    from backend.domain.contracts import AcceptAction
    from backend.domain.evaluate import scenarios
    monkeypatch.setattr(negotiation, "call_agent_bounded", lambda *args: AcceptAction(type="accept", offer_id="o_invalid"))
    result = evaluate_with_conversation(None, scenarios()[0][2], True, limits=negotiation.NegotiationLimits())
    assert result["reason_code"] == "invalid_action" and result["conversation"] == []
    assert result["attempts"][0]["proposed_action"]["type"] == "accept"
    assert result["attempts"][0]["recorded_in_conversation"] is False


def test_failed_attempt_is_logged(monkeypatch):
    from backend.domain import negotiation
    from backend.domain.evaluate import scenarios
    def fail(*args):
        raise ModelCallError("timeout")
    monkeypatch.setattr(negotiation, "call_agent_bounded", fail)
    result = evaluate_with_conversation(None, scenarios()[0][2], True, limits=negotiation.NegotiationLimits())
    assert result["reason_code"] == "timeout" and result["conversation"] == []
    assert result["attempts"][0]["error_code"] == "timeout"
