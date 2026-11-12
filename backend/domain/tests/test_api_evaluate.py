"""Checks for the isolated synthetic HTTP evaluation harness."""

import os

import pytest

from backend.domain.api_evaluate import main, run_case
from backend.domain.evaluate import scenarios
from backend.domain.model_client import ModelCallError
from backend.domain.negotiation_fixtures import FixtureAgents


class UnavailableAgent:
    def generate_buyer(self, data):
        raise ModelCallError("rate_limited")


@pytest.fixture
def test_database():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL required for PostgreSQL HTTP integration")
    return dsn


@pytest.mark.parametrize("name,expected,scenario", scenarios())
def test_six_scenarios_send_and_receive_using_real_router(test_database, name, expected, scenario):
    result = run_case(test_database, scenario, expected, FixtureAgents())
    assert result["send_receive_consistent"]
    assert result["matches_expected"] is True
    assert result["quote_issued"] is expected
    assert all(call["code"] == "ok" for call in result["calls"])


def test_provider_error_is_incomplete_and_sanitized(test_database):
    _, expected, scenario = scenarios()[0]
    result = run_case(test_database, scenario, expected, UnavailableAgent())
    assert result["status"] == "retryable_error"
    assert result["matches_expected"] is None and not result["quote_issued"]
    assert result["calls"][0]["code"] == "rate_limited"
    assert "budget" not in str(result) and "api_key" not in str(result)


def test_cli_requires_explicit_test_database(monkeypatch, capsys):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "must_not_be_used")
    assert main(["--candidate", "fixture"]) == 1
    assert "TEST_DATABASE_URL is required" in capsys.readouterr().err
