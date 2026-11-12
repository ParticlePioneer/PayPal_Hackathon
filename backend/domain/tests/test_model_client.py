"""Real SDK/mock-HTTP integration plus strict response and role boundary tests."""

import json
import socket
from unittest.mock import MagicMock

from google import genai
from google.genai import errors, types
import httpx
import pytest

from backend.domain.contracts import (
    ACTION_ADAPTER, BuyerAgentInput, SellerAgentInput,
    OfferAction, PublicEvent, SellerPolicy, SellerPrivateInput, SellerStockBatch,
    SharedNegotiationContext,
)
from backend.domain.fixtures import buyer_fixture, split_offer_fixture
from backend.domain.model_client import (
    ActionEnvelope, GeminiActionClient, ModelCallError, _parse_response, response_schema,
)
from backend.domain.model_config import GeminiSettings


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests must not open sockets")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def settings():
    return GeminiSettings(api_key="fake-test-api-key", model="gemini-test-model")


def buyer_input():
    buyer = buyer_fixture()
    return BuyerAgentInput(private=buyer, shared=SharedNegotiationContext(requirements=buyer.requirements))


def seller_input():
    # Deliberately synthetic values to detect cross-role leakage; not merchant policy.
    return SellerAgentInput(
        private=SellerPrivateInput(
            sku="shirts", policy=SellerPolicy(minimum_total_cents=12345),
            stock_batches=(SellerStockBatch(
                batch_id="private_stock_marker", color="navy", available_qty=77, deliver_by="2026-11-13",
            ),),
        ),
        shared=buyer_input().shared,
    )


def action(kind="ask"):
    return {
        "ask": {"type": "ask", "topic": "delivery_options"},
        "offer": {"type": "offer", "terms": split_offer_fixture().model_dump(mode="json")},
        "counter": {"type": "counter", "offer_id": "offer_previous", "terms": split_offer_fixture().model_dump(mode="json")},
        "accept": {"type": "accept", "offer_id": "offer_previous"},
        "decline": {"type": "decline", "reason_code": "terms_unacceptable"},
    }[kind]


def response_body(text=None, finish="STOP"):
    return {"candidates": [{
        "content": {"role": "model", "parts": [{"text": text if text is not None else json.dumps({"action": action()})}]},
        "finishReason": finish,
    }]}


def response(text=None, finish="STOP"):
    return types.GenerateContentResponse.model_validate(response_body(text, finish))


@pytest.fixture
def sdk(monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.models.generate_content.return_value = response()
    monkeypatch.setattr("backend.domain.model_client.genai.Client", factory)
    return factory, client


@pytest.mark.parametrize("kind", ["ask", "offer", "counter", "accept", "decline"])
def test_every_action_returns_existing_validated_contract(kind):
    result = _parse_response(response(json.dumps({"action": action(kind)})))
    assert result == ACTION_ADAPTER.validate_python(action(kind))


@pytest.mark.parametrize("role", ["buyer", "seller"])
def test_separate_role_requests_and_client_cleanup(sdk, role):
    factory, client = sdk
    model = GeminiActionClient(settings())
    result = getattr(model, f"generate_{role}")(buyer_input() if role == "buyer" else seller_input())
    assert result.type == "ask"
    factory.assert_called_once()
    options = factory.call_args.kwargs
    assert options["api_key"] == "fake-test-api-key"
    assert options["vertexai"] is False and options["enterprise"] is False
    http = options["http_options"]
    assert http.base_url == "https://generativelanguage.googleapis.com"
    assert http.timeout == 30000 and http.retry_options.attempts == 1
    assert http.api_version == "v1beta"
    request = client.models.generate_content.call_args.kwargs
    assert request["model"] == "gemini-test-model"
    data = json.loads(request["contents"])
    assert data["role"] == role
    if role == "buyer":
        assert data["input"]["private"]["budget_cents"] == 36000
        assert "minimum_total_cents" not in request["contents"]
        assert "private_stock_marker" not in request["contents"]
    else:
        assert data["input"]["private"]["policy"]["minimum_total_cents"] == 12345
        assert "private_stock_marker" in request["contents"]
        assert "budget_cents" not in request["contents"]
    assert "fake-test-api-key" not in request["contents"]
    config = request["config"]
    assert config.response_json_schema == response_schema()
    assert config.response_mime_type == "application/json"
    assert config.candidate_count is None and config.max_output_tokens == 2048
    assert config.automatic_function_calling.disable is True
    assert config.thinking_config is None
    factory.return_value.__exit__.assert_called_once()
    client.models.generate_content.assert_called_once()


def test_role_calls_do_not_reuse_another_roles_history(sdk):
    _, client = sdk
    model = GeminiActionClient(settings())
    model.generate_buyer(buyer_input())
    model.generate_seller(seller_input())
    first, second = [call.kwargs["contents"] for call in client.models.generate_content.call_args_list]
    assert "budget_cents" in first and "budget_cents" not in second
    assert "minimum_total_cents" in second and "minimum_total_cents" not in first


def test_seller_receives_active_offer_and_private_option_for_counter(sdk):
    _, client = sdk
    option = split_offer_fixture()
    buyer_offer = option.model_copy(update={"total_cents": 30000})
    event = PublicEvent(event_id="e1", sequence=1, actor="buyer",
                        action=OfferAction(type="offer", terms=buyer_offer), issued_offer_id="o1")
    original = seller_input()
    data = SellerAgentInput(
        private=original.private.model_copy(update={"offer_options": (option,)}),
        shared=SharedNegotiationContext(requirements=original.shared.requirements, events=(event,)),
    )
    client.models.generate_content.return_value = response(json.dumps({"action": {
        "type": "counter", "offer_id": "o1", "terms": option.model_dump(mode="json")}}))

    result = GeminiActionClient(settings()).generate_seller(data)
    request = client.models.generate_content.call_args.kwargs
    payload = json.loads(request["contents"])["input"]
    assert payload["shared"]["events"][0]["issued_offer_id"] == "o1"
    assert payload["private"]["offer_options"][0] == option.model_dump(mode="json")
    assert "budget_cents" not in request["contents"]
    assert "counter the active buyer offer" in request["config"].system_instruction
    assert result.type == "counter" and result.offer_id == "o1" and result.terms == option


def test_buyer_guidance_allows_nonpreferred_allowed_color(sdk):
    _, client = sdk
    GeminiActionClient(settings()).generate_buyer(buyer_input())
    instruction = client.models.generate_content.call_args.kwargs["config"].system_instruction
    assert "other allowed colors and split deliveries are acceptable" in instruction
    assert "counter the active buyer offer" not in instruction


@pytest.mark.parametrize("role,invalid", [
    ("buyer", seller_input()), ("seller", buyer_input()),
    ("buyer", {"private": "raw data"}), ("seller", None),
])
def test_wrong_role_input_rejected_before_client_construction(sdk, role, invalid):
    factory, _ = sdk
    with pytest.raises(ModelCallError, match="Agent input"):
        getattr(GeminiActionClient(settings()), f"generate_{role}")(invalid)
    factory.assert_not_called()


def test_bypassed_pydantic_validation_is_revalidated(sdk):
    factory, _ = sdk
    original = buyer_input()
    broken = original.model_copy(update={"private": original.private.model_copy(update={"budget_cents": "leak_marker"})})
    with pytest.raises(ModelCallError) as caught:
        GeminiActionClient(settings()).generate_buyer(broken)
    assert caught.value.code == "invalid_input" and "leak_marker" not in str(caught.value)
    factory.assert_not_called()


def test_oversized_input_rejected_without_network(sdk, monkeypatch):
    import backend.domain.model_client as module
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", 10)
    factory, _ = sdk
    with pytest.raises(ModelCallError):
        GeminiActionClient(settings()).generate_buyer(buyer_input())
    factory.assert_not_called()


@pytest.mark.parametrize("payload", [
    "not json", "```json\n{}\n```", "null", "[]", "{}",
    '{"action":{"type":"approve"}}',
    '{"action":{"type":"accept"}}',
    '{"action":{"type":"ask","topic":"delivery_options","text":"private_marker"}}',
    '{"action":{"type":"ask","topic":"delivery_options"},"reasoning":"private_marker"}',
    '{"action":{"type":"ask","topic":"delivery_options","type":"decline"}}',
    '{"action":{"type":"ask","topic":"delivery_options"},"action":{"type":"ask","topic":"color_options"}}',
    '{"action":{"type":"offer","terms":{"currency":"USD","total_cents":NaN,"lines":[]}}}',
])
def test_malformed_response_never_repairs_or_echoes_raw_output(payload):
    with pytest.raises(ModelCallError) as caught:
        _parse_response(response(payload))
    assert caught.value.code == "invalid_response"
    assert "private_marker" not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize("value", [0, -1, True, "35400", 35400.0])
def test_provider_action_cents_are_still_strict(value):
    payload = action("offer")
    payload["terms"]["total_cents"] = value
    with pytest.raises(ModelCallError):
        _parse_response(response(json.dumps({"action": payload})))


@pytest.mark.parametrize("finish,code", [
    ("MAX_TOKENS", "incomplete_response"), (None, "incomplete_response"),
    ("SAFETY", "blocked_response"), ("RECITATION", "blocked_response"),
    ("OTHER", "incomplete_response"),
])
def test_incomplete_or_blocked_output_is_not_accepted_even_when_json_is_valid(finish, code):
    with pytest.raises(ModelCallError) as caught:
        _parse_response(response(finish=finish))
    assert caught.value.code == code


@pytest.mark.parametrize("body,code", [
    ({}, "empty_response"),
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked_response"),
    ({"candidates": [{"finishReason": "STOP"}]}, "empty_response"),
    (response_body("") , "empty_response"),
    ({"candidates": response_body()["candidates"] * 2}, "invalid_response"),
    ({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"functionCall": {"name": "pay", "args": {}}}]}}]}, "invalid_response"),
])
def test_empty_ambiguous_and_tool_outputs(body, code):
    with pytest.raises(ModelCallError) as caught:
        _parse_response(types.GenerateContentResponse.model_validate(body))
    assert caught.value.code == code


def test_reasoning_is_never_used_as_action_text():
    body = response_body()
    body["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "private_reasoning_marker"})
    assert _parse_response(types.GenerateContentResponse.model_validate(body)).type == "ask"
    body["candidates"][0]["content"]["parts"] = [{"thought": True, "text": json.dumps({"action": action()})}]
    with pytest.raises(ModelCallError, match="no usable"):
        _parse_response(types.GenerateContentResponse.model_validate(body))


def test_oversized_response(monkeypatch):
    monkeypatch.setattr("backend.domain.model_client.MAX_RESPONSE_BYTES", 10)
    with pytest.raises(ModelCallError):
        _parse_response(response())


@pytest.mark.parametrize("invalid", [None, {}, "raw provider output"])
def test_unexpected_sdk_response_type_is_sanitized(invalid):
    with pytest.raises(ModelCallError) as caught:
        _parse_response(invalid)
    assert caught.value.code == "invalid_response"


def test_invalid_unicode_response_is_sanitized():
    with pytest.raises(ModelCallError) as caught:
        _parse_response(response("\ud800"))
    assert caught.value.code == "invalid_response"


@pytest.mark.parametrize("status,code,retryable", [
    (400, "request_rejected", False), (401, "credentials_rejected", False),
    (403, "credentials_rejected", False), (404, "model_unavailable", False),
    (408, "timeout", True), (429, "rate_limited", True),
    (500, "provider_unavailable", True), (503, "provider_unavailable", True),
    (504, "timeout", True), (418, "provider_error", False),
])
def test_sdk_http_errors_are_sanitized_and_not_retried(sdk, status, code, retryable):
    factory, client = sdk
    client.models.generate_content.side_effect = errors.APIError(status, {"error": {"message": "private_provider_marker"}})
    with pytest.raises(ModelCallError) as caught:
        GeminiActionClient(settings()).generate_buyer(buyer_input())
    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert caught.value.provider_status == status
    assert "private_provider_marker" not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    client.models.generate_content.assert_called_once()
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("exception,code", [
    (httpx.ReadTimeout("private_marker"), "timeout"),
    (TimeoutError("private_marker"), "timeout"),
    (httpx.ConnectError("private_marker"), "network_error"),
    (OSError("private_marker"), "network_error"),
    (RuntimeError("private_marker"), "provider_error"),
])
def test_other_provider_failures_are_sanitized(sdk, exception, code):
    _, client = sdk
    client.models.generate_content.side_effect = exception
    with pytest.raises(ModelCallError) as caught:
        GeminiActionClient(settings()).generate_buyer(buyer_input())
    assert caught.value.code == code and "private_marker" not in str(caught.value)


def test_schema_adaptation_retains_contracts_without_provider_discriminator():
    schema = response_schema()
    encoded = json.dumps(schema)
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert schema["required"] == ["action"]
    assert len(schema["properties"]["action"]["anyOf"]) == 5
    assert "oneOf" not in encoded and "discriminator" not in encoded and '"const"' not in encoded
    assert schema["$defs"]["OfferTerms"]["properties"]["total_cents"]["minimum"] == 1
    assert schema["$defs"]["AskAction"]["properties"]["type"]["enum"] == ["ask"]
    assert ActionEnvelope.model_json_schema()["properties"]["action"]["discriminator"]["propertyName"] == "type"


@pytest.mark.parametrize("status", [200, 429, 503])
def test_real_sdk_serialization_and_http_transport_without_network(monkeypatch, status):
    # Unrelated SDK environment settings must not change credentials or route.
    monkeypatch.setenv("GOOGLE_API_KEY", "opposite_key_marker")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://untrusted.invalid")
    real_client = genai.Client
    requests = []

    def handle(request):
        requests.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "private_provider_marker", "status": "UNAVAILABLE"}})
        return httpx.Response(200, json=response_body())

    closed = []

    class RecordingTransport(httpx.MockTransport):
        def close(self):
            closed.append(True)
            super().close()

    transport = RecordingTransport(handle)

    def factory(**kwargs):
        # Let the SDK own its HTTP client, as production does. A separately
        # injected httpx_client remains caller-owned under the SDK contract.
        options = kwargs["http_options"].model_copy(update={"client_args": {"transport": transport, "trust_env": False}})
        return real_client(**{**kwargs, "http_options": options})

    monkeypatch.setattr("backend.domain.model_client.genai.Client", factory)
    client = GeminiActionClient(settings())
    if status == 200:
        assert client.generate_buyer(buyer_input()).type == "ask"
    else:
        with pytest.raises(ModelCallError):
            client.generate_buyer(buyer_input())
    assert len(requests) == 1  # Actual SDK retries are disabled.
    req = requests[0]
    assert req.url.host == "generativelanguage.googleapis.com"
    assert req.url.path == "/v1beta/models/gemini-test-model:generateContent"
    assert "key=" not in str(req.url)
    assert req.headers["x-goog-api-key"] == "fake-test-api-key"
    body = json.loads(req.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "candidateCount" not in body["generationConfig"]
    assert body["generationConfig"]["responseJsonSchema"] == response_schema()
    assert "fake-test-api-key" not in req.content.decode()
    assert closed == [True]


def test_thinking_level_is_explicit_and_applied_to_sdk(sdk):
    _, client = sdk
    configured = GeminiSettings(api_key="fake-test-api-key", model="gemini-test-model", thinking_level="low")
    GeminiActionClient(configured).generate_buyer(buyer_input())
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


@pytest.mark.parametrize("status", [200, 429])
def test_opt_in_http_trace_records_success_and_error(monkeypatch, tmp_path, status):
    real_client = genai.Client
    body = response_body() if status == 200 else {"error": {"code": 429, "message": "quota fake-test-api-key"}}
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body, headers={"set-cookie": "secret"}))

    def factory(**kwargs):
        options = kwargs["http_options"]
        client_args = {**options.client_args, "transport": transport, "trust_env": False}
        return real_client(**{**kwargs, "http_options": options.model_copy(update={"client_args": client_args})})

    monkeypatch.setattr("backend.domain.model_client.genai.Client", factory)
    path = tmp_path / "trace.jsonl"
    client = GeminiActionClient(settings(), response_trace=path)
    client.trace_case = "test_case"
    if status == 200:
        client.generate_buyer(buyer_input())
    else:
        with pytest.raises(ModelCallError):
            client.generate_buyer(buyer_input())
    record = json.loads(path.read_text(encoding="utf-8"))
    assert (record["case"], record["role"], record["status_code"]) == ("test_case", "buyer", status)
    assert record["headers"]["set-cookie"] == "[REDACTED]"
    assert "fake-test-api-key" not in path.read_text(encoding="utf-8")
    assert json.loads(record["body"])["error"]["code"] == 429 if status == 429 else json.loads(record["body"]) == body
