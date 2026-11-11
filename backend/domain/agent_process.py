"""Run one agent call in a disposable process with a parent-enforced deadline."""

from contextlib import redirect_stderr, redirect_stdout
import json
import multiprocessing
import os
import time

from pydantic import ValidationError

from .contracts import BuyerAgentInput, SellerAgentInput, ACTION_ADAPTER
from .model_client import ModelCallError, MAX_INPUT_BYTES, MAX_RESPONSE_BYTES, _ERROR_MESSAGES


def _worker(output, source, actor, agent_input):
    # Never let an SDK traceback or debug print reach the terminal transcript.
    with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
        try:
            action = getattr(source, f"generate_{actor}")(agent_input)
            action = ACTION_ADAPTER.validate_python(action)
            payload = json.dumps({"action": action.model_dump(mode="json")}).encode("utf-8")
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ModelCallError("invalid_response")
        except ModelCallError as error:
            code = error.code if error.code in _ERROR_MESSAGES else "provider_error"
            payload = json.dumps({"error": code}).encode("utf-8")
        except ValidationError:
            payload = b'{"error":"invalid_response"}'
        except Exception:
            payload = b'{"error":"provider_error"}'
        try:
            output.send_bytes(payload)
        finally:
            output.close()


def call_agent_bounded(source, actor, agent_input, timeout_ms: int):
    """Only the selected role's private input crosses into the child process.

    A timed-out process is terminated and reaped; no abandoned thread or late
    model result can continue the conversation. Cleanup has at most two seconds
    of grace beyond the requested call timeout. The source is trusted code.
    """
    cls = BuyerAgentInput if actor == "buyer" else SellerAgentInput if actor == "seller" else None
    if cls is None or not isinstance(agent_input, cls) or type(timeout_ms) is not int or timeout_ms <= 0:
        raise ModelCallError("invalid_input")
    try:
        checked = cls.model_validate(agent_input)
        if len(checked.model_dump_json().encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Oversized agent input")
    except (ValidationError, ValueError):
        raise ModelCallError("invalid_input") from None
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(writer, source, actor, checked), daemon=True)
    started = False
    deadline = time.monotonic() + timeout_ms / 1000
    try:
        process.start()
        started = True
        writer.close()
        if not reader.poll(max(0.0, deadline - time.monotonic())):
            raise ModelCallError("timeout")
        payload = reader.recv_bytes(MAX_RESPONSE_BYTES)
        if time.monotonic() >= deadline:
            raise ModelCallError("timeout")
        message = json.loads(payload)
        if isinstance(message, dict) and set(message) == {"error"} and message["error"] in _ERROR_MESSAGES:
            raise ModelCallError(message["error"])
        if not isinstance(message, dict) or set(message) != {"action"}:
            raise ModelCallError("invalid_response")
        return ACTION_ADAPTER.validate_python(message["action"])
    except ModelCallError:
        raise
    except (ValidationError, ValueError, TypeError):
        raise ModelCallError("invalid_response") from None
    except Exception:
        raise ModelCallError("provider_error") from None
    finally:
        reader.close()
        writer.close()
        if started:
            process.join(timeout=0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            if not process.is_alive():
                process.close()
