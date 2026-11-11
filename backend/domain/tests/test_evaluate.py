"""Synthetic evaluation mechanics; no model calls or frozen datasets."""

import json

import pytest

from backend.domain import negotiation
from backend.domain.contracts import AcceptAction, AskAction, OfferAction, OfferTerms
from backend.domain.evaluate import comparison, evaluate, main, scenarios
from backend.domain.fixtures import split_offer_fixture
from backend.domain.negotiation import NegotiationLimits
from backend.domain.negotiation_fixtures import FixtureAgents


@pytest.fixture(autouse=True)
def direct_agents(monkeypatch):
    monkeypatch.setattr(negotiation, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data))


def test_six_labeled_cases_compare_both_simulated_sources_under_same_limit():
    report = comparison(FixtureAgents(), candidate_kind="fixture")
    assert report["candidate_kind"] == "fixture" and report["synthetic_policy_and_stock"]
    assert report["max_turns"] == 6 and not report["quote_issuance_tested"]
    assert [case["case"] for case in report["cases"]] == [
        "feasible_split", "impossible_deadline", "budget_shortfall", "forbidden_color", "competing_buyer_depleted", "ordinary_order"]
    for case in report["cases"]:
        for key in ("baseline", "candidate"):
            result = case[key]
            assert result["matches_expected"] is True
            assert result["turns"] <= 6 and not result["quote_issued"]
            assert result["server_accepted_terms"] == case["expected_deal"]


class BadPriceAgents:
    def generate_buyer(self, data):
        proposal = next((event for event in reversed(data.shared.events) if event.issued_offer_id), None)
        return AcceptAction(type="accept", offer_id=proposal.issued_offer_id) if proposal else AskAction(type="ask", topic="delivery_options")

    def generate_seller(self, data):
        terms = OfferTerms.model_validate({**split_offer_fixture().model_dump(), "total_cents": 40000})
        return OfferAction(type="offer", terms=terms)


def test_ineligible_proposal_is_counted_but_never_accepted_or_quoted():
    _, expected, scenario = scenarios()[0]
    result = evaluate(BadPriceAgents(), scenario, expected, limits=NegotiationLimits())
    assert result["ineligible_proposals"] == 1 and result["reason_code"] == "ineligible_offer"
    assert not result["server_accepted_terms"] and not result["quote_issued"]
    assert result["matches_expected"] is False


def test_malformed_agent_action_is_reported_without_counting_a_deal():
    class MalformedAgents:
        def generate_buyer(self, data):
            return {"type": "approve", "private_reasoning": "secret_marker"}
    _, expected, scenario = scenarios()[0]
    result = evaluate(MalformedAgents(), scenario, expected, limits=NegotiationLimits())
    assert result["status"] == "error" and result["invalid_action"] is True
    assert result["matches_expected"] is None and not result["server_accepted_terms"]
    assert "secret_marker" not in json.dumps(result)


def test_timeout_is_incomplete_not_a_correct_no_deal():
    from backend.domain.model_client import ModelCallError
    class TimeoutAgents:
        def generate_buyer(self, data):
            raise ModelCallError("timeout")
    _, expected, scenario = scenarios()[0]
    result = evaluate(TimeoutAgents(), scenario, expected, limits=NegotiationLimits())
    assert result["status"] == "retryable_error" and result["reason_code"] == "timeout"
    assert result["matches_expected"] is None and not result["server_accepted_terms"]


def test_fixture_cli_never_reads_model_configuration_or_fakes_live_counts(monkeypatch, capsys):
    monkeypatch.setattr("backend.domain.evaluate.GeminiSettings.from_environment", lambda **_: pytest.fail("fixture mode loaded credentials"))
    assert main(["--candidate", "fixture"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_kind"] == "fixture" and len(report["cases"]) == 6
    assert "api_key" not in json.dumps(report) and "minimum_total_cents" not in json.dumps(report)


def test_candidate_label_must_be_explicit():
    with pytest.raises(ValueError):
        comparison(FixtureAgents(), candidate_kind="ai")


def test_incomplete_comparison_exits_unsuccessfully(monkeypatch, capsys):
    partial = {"cases": [{"candidate": {"matches_expected": None}, "baseline": {"matches_expected": True}}]}
    monkeypatch.setattr("backend.domain.evaluate.comparison", lambda *args, **kwargs: partial)
    assert main(["--candidate", "fixture"]) == 1
    assert json.loads(capsys.readouterr().out)["cases"][0]["candidate"]["matches_expected"] is None


def test_falsey_invalid_limits_are_not_silently_defaulted():
    with pytest.raises(ValueError):
        comparison(FixtureAgents(), candidate_kind="fixture", limits=0)
