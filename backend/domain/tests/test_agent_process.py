"""Offline integration of the real spawn/pipe/termination boundary."""

import multiprocessing
import time

import pytest

from backend.domain.agent_process import call_agent_bounded
from backend.domain.contracts import AskAction, BuyerAgentInput, SellerAgentInput, SharedNegotiationContext
from backend.domain.model_client import ModelCallError
from backend.domain.negotiation_fixtures import fixture_scenario


class CheckingAgent:
    def generate_buyer(self, data):
        assert "minimum_total_cents" not in data.model_dump_json()
        return AskAction(type="ask", topic="delivery_options")

    def generate_seller(self, data):
        assert "budget_cents" not in data.model_dump_json()
        return AskAction(type="ask", topic="revised_offer")


class HangingAgent:
    def __init__(self, marker):
        self.marker = marker

    def generate_buyer(self, data):
        self.marker.write_text("entered", encoding="utf-8")
        time.sleep(60)
        return AskAction(type="ask", topic="delivery_options")


class MalformedAgent:
    def generate_buyer(self, data):
        return {"type": "approve", "private_reasoning": "private_marker"}


class FailedAgent:
    def generate_buyer(self, data):
        raise ModelCallError("rate_limited")


class CrashedAgent:
    def generate_buyer(self, data):
        raise RuntimeError("private_crash_marker")


def role_input(role="buyer"):
    scenario = fixture_scenario(30000)
    shared = SharedNegotiationContext(requirements=scenario.buyer.requirements)
    return BuyerAgentInput(private=scenario.buyer, shared=shared) if role == "buyer" else SellerAgentInput(private=scenario.seller, shared=shared)


@pytest.mark.parametrize("role", ["buyer", "seller"])
def test_real_child_receives_only_selected_role_and_is_reaped(role):
    before = {p.pid for p in multiprocessing.active_children()}
    assert call_agent_bounded(CheckingAgent(), role, role_input(role), 20000).type == "ask"
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_hung_child_is_terminated_and_never_finishes_late(tmp_path):
    before = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    marker = tmp_path / "worker-started.txt"
    with pytest.raises(ModelCallError) as caught:
        call_agent_bounded(HangingAgent(marker), "buyer", role_input(), 10000)
    assert caught.value.code == "timeout"
    assert marker.read_text(encoding="utf-8") == "entered"
    assert time.monotonic() - start < 15
    assert {p.pid for p in multiprocessing.active_children()} == before


@pytest.mark.parametrize("source,code", [(MalformedAgent(), "invalid_response"), (FailedAgent(), "rate_limited"), (CrashedAgent(), "provider_error")])
def test_child_failures_are_sanitized(source, code):
    with pytest.raises(ModelCallError) as caught:
        call_agent_bounded(source, "buyer", role_input(), 20000)
    assert caught.value.code == code
    assert "private_marker" not in str(caught.value) and "private_crash_marker" not in str(caught.value)


@pytest.mark.parametrize("role,timeout", [("system", 1000), ("buyer", 0), ("buyer", True)])
def test_invalid_boundary_arguments(role, timeout):
    with pytest.raises(ModelCallError):
        call_agent_bounded(CheckingAgent(), role, role_input(), timeout)


def test_opposite_role_input_rejected():
    with pytest.raises(ModelCallError):
        call_agent_bounded(CheckingAgent(), "buyer", role_input("seller"), 1000)
