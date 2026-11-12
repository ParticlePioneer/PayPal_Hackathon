"""OpenRouter chat-completions adapter for validated negotiation actions."""
import json
from pathlib import Path
import time

import httpx
from google.genai import types

from backend.domain.model_client import (
    MAX_RESPONSE_BYTES, ModelCallError, _input_json, _instruction, _parse_response,
    response_schema,
)
from .openrouter_config import Settings


def provider_error(status):
    return {400: "request_rejected", 401: "credentials_rejected", 402: "credentials_rejected",
            403: "credentials_rejected", 404: "model_unavailable", 408: "timeout",
            429: "rate_limited", 504: "timeout"}.get(
                status, "provider_unavailable" if status >= 500 else "provider_error")


def parse_completion(body):
    """Reject missing, blocked, nonterminal and tool-based output."""
    try:
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            status = body["error"].get("code")
            if isinstance(status, int) and not isinstance(status, bool) and 400 <= status <= 599:
                raise ModelCallError(provider_error(status), provider_status=status)
            raise ModelCallError("provider_error")
        choices = body["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ModelCallError("invalid_response")
        choice = choices[0]
        if choice.get("finish_reason") == "content_filter":
            raise ModelCallError("blocked_response")
        if choice.get("finish_reason") != "stop":
            raise ModelCallError("incomplete_response")
        message = choice["message"]
        if message.get("refusal") or message.get("tool_calls") or message.get("function_call"):
            raise ModelCallError("blocked_response" if message.get("refusal") else "invalid_response")
        content = message.get("content")
        if content is None or content == "":
            raise ModelCallError("empty_response")
        if not isinstance(content, str):
            raise ModelCallError("invalid_response")
        # The existing validator rejects duplicates, nonfinite values, extra keys and wrong actions.
        return _parse_response(types.GenerateContentResponse(candidates=[types.Candidate(
            finish_reason=types.FinishReason.STOP,
            content=types.Content(parts=[types.Part(text=content)]),
        )]))
    except ModelCallError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ModelCallError("invalid_response") from None


class OpenRouterActionClient:
    def __init__(self, settings: Settings, *, response_trace: Path | None = None):
        self.settings = settings
        self.trace_path = response_trace
        self.trace_case = None

    def generate_buyer(self, agent_input):
        return self._generate("buyer", _input_json("buyer", agent_input))

    def generate_seller(self, agent_input):
        return self._generate("seller", _input_json("seller", agent_input))

    def _generate(self, role, payload):
        request = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": _instruction(role) + " Return JSON matching this schema: " + json.dumps(response_schema())},
                {"role": "user", "content": payload},
            ],
            "response_format": {"type": "json_object"},
            "provider": {"require_parameters": True},
            "max_tokens": self.settings.max_output_tokens,
            "stream": False,
        }
        start = time.monotonic()
        try:
            with httpx.Client(timeout=self.settings.timeout_ms / 1000, follow_redirects=False) as client:
                response = client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer " + self.settings.api_key}, json=request)
            if self.trace_path is not None:
                redacted = {k: ("[REDACTED]" if k.lower() in {"set-cookie", "authorization", "proxy-authorization"}
                                else v.replace(self.settings.api_key, "[REDACTED]")) for k, v in response.headers.items()}
                record = {"case": self.trace_case, "role": role, "requested_model": self.settings.model,
                          "status_code": response.status_code, "http_version": response.http_version,
                          "elapsed_ms": round((time.monotonic() - start) * 1000), "headers": redacted,
                          "body": response.text.replace(self.settings.api_key, "[REDACTED]")}
                with self.trace_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=True) + "\n")
            if response.status_code != 200:
                status = response.status_code
                raise ModelCallError(provider_error(status), provider_status=status)
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ModelCallError("invalid_response")
            return parse_completion(response.json())
        except ModelCallError:
            raise
        except httpx.TimeoutException:
            raise ModelCallError("timeout") from None
        except (httpx.TransportError, OSError):
            raise ModelCallError("network_error") from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ModelCallError("invalid_response") from None
