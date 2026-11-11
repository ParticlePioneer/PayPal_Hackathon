"""Privacy and timeout checks through the A4 HTTP service."""

import multiprocessing
import time

from backend.domain import turns
from backend.domain.agent_process import call_agent_bounded
from backend.domain.contracts import AskAction
from backend.domain.tests.test_api_postgres import environment, create, seed, turn


def test_only_the_current_roles_private_input_reaches_agent(environment, monkeypatch):
    client, service, scenario = environment
    seed(service, scenario)
    observed = []
    def observe(source, actor, data, timeout):
        observed.append((actor, data.model_dump_json()))
        return getattr(source, f"generate_{actor}")(data)
    monkeypatch.setattr(turns, "call_agent_bounded", observe)
    view = create(client, scenario)
    for version in range(3):
        response = turn(client, view["id"], version)
        assert response.status_code == 200
        view = response.json()
        assert "budget_cents" not in response.text and "minimum_total_cents" not in response.text
        assert "friday_navy" not in response.text and "36000" not in response.text and "30000" not in response.text
    assert [actor for actor, _ in observed] == ["buyer", "seller", "buyer"]
    for actor, text in observed:
        if actor == "buyer":
            assert "budget_cents" in text and "minimum_total_cents" not in text and "stock_batches" not in text
        else:
            assert "minimum_total_cents" in text and "stock_batches" in text and "budget_cents" not in text


class HangingAgent:
    def __init__(self, marker):
        self.marker = marker

    def generate_buyer(self, data):
        self.marker.write_text("entered", encoding="utf-8")
        time.sleep(60)
        return AskAction(type="ask", topic="delivery_options")


def test_real_hung_worker_times_out_without_saving_action(environment, monkeypatch, tmp_path):
    client, service, scenario = environment
    seed(service, scenario)
    marker = tmp_path / "a5-worker-entered"
    service.agent_source = HangingAgent(marker)
    service.timeout_ms = 10000
    monkeypatch.setattr(turns, "call_agent_bounded", call_agent_bounded)
    before = {child.pid for child in multiprocessing.active_children()}
    view = create(client, scenario)
    started = time.monotonic()
    response = turn(client, view["id"], 0)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "retryable_error" and result["messages"] == [] and result["quote"] is None
    assert marker.read_text(encoding="utf-8") == "entered"
    assert time.monotonic() - started < 16
    assert {child.pid for child in multiprocessing.active_children()} == before
