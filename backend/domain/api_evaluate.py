"""Compare six synthetic cases through the existing A4 HTTP turn/read endpoints.

Only TEST_DATABASE_URL is accepted. Test-owned schemas are created and removed;
no public server or payment calls are made. Live mode makes real Gemini calls.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql

from . import turns
from .api import NegotiationService, create_router
from .database import DomainDatabase
from .evaluate import scenarios
from .migrate import apply_migrations
from .model_client import ModelCallError
from .openrouter_client import OpenRouterActionClient
from .openrouter_config import Settings as OpenRouterSettings
from .negotiation_fixtures import FixtureAgents
from .quotes import QuoteAdapter


def run_case(dsn, scenario, expected_deal, source):
    """Drive POST /turn and GET /id through the real router and PostgreSQL."""
    schema = "a5_http_" + uuid4().hex
    created = False
    calls = []
    original = turns.call_agent_bounded

    def measured(agent, actor, data, timeout_ms):
        start = time.monotonic()
        code = "ok"
        try:
            return original(agent, actor, data, timeout_ms)
        except ModelCallError as error:
            code = error.code  # Known sanitized code; no provider body or inputs.
            raise
        except Exception:
            code = "unexpected_error"
            raise
        finally:
            calls.append({"role": actor, "code": code,
                          "elapsed_ms": round((time.monotonic() - start) * 1000)})

    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        created = True
        database = DomainDatabase(dsn, schema=schema)
        apply_migrations(database)
        quotes = QuoteAdapter(database)
        for batch in scenario.seller.stock_batches:
            quotes.add_stock_batch(scenario.seller.sku, batch)
        service = NegotiationService(quotes, lambda _: scenario.seller, source)
        app = FastAPI()
        app.include_router(create_router(service, session_dependency=lambda: "synthetic_buyer"))
        payload = {**scenario.buyer.requirements.model_dump(mode="json"),
                   "budget_cents": scenario.buyer.budget_cents}
        turns.call_agent_bounded = measured
        with TestClient(app) as client:
            response = client.post("/api/negotiations", json=payload)
            response.raise_for_status()
            view = response.json()
            for _ in range(6):
                if view["status"] != "negotiating":
                    break
                response = client.post(f"/api/negotiations/{view['id']}/turn",
                                       json={"expected_version": view["version"]})
                response.raise_for_status()
                view = response.json()
                restored = client.get(f"/api/negotiations/{view['id']}")
                restored.raise_for_status()
                if restored.json() != view:
                    raise RuntimeError("HTTP read did not restore the submitted turn")
            completed = view["status"] in {"quoted", "no_deal"}
            quoted = view["status"] == "quoted" and view["quote"] is not None
            return {"status": view["status"], "turns": len(calls),
                    "quote_issued": quoted, "matches_expected": (quoted == expected_deal) if completed else None,
                    "send_receive_consistent": True, "calls": calls}
    finally:
        turns.call_agent_bounded = original
        if created:
            if not re.fullmatch(r"a5_http_[0-9a-f]{32}", schema):
                raise RuntimeError("Invalid test schema")
            with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare synthetic cases over local A4 HTTP endpoints")
    parser.add_argument("--candidate", required=True, choices=("fixture", "live"))
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("TEST_DATABASE_URL is required and must be disposable.", file=sys.stderr)
        return 1
    try:
        model = None
        if args.candidate == "live":
            path = args.env_file or Path(__file__).resolve().parents[2] / ".env"
            settings = OpenRouterSettings.from_environment(env_file=path)
            source, model = OpenRouterActionClient(settings), settings.model
        else:
            source = FixtureAgents()
        cases = []
        for name, expected, scenario in scenarios():
            result = run_case(dsn, scenario, expected, source)
            cases.append({"case": name, "expected_deal": expected, **result})
        print(json.dumps({"candidate_kind": args.candidate, "candidate_model": model,
                          "synthetic_policy_and_stock": True, "transport": "in_process_http",
                          "cases": cases}, separators=(",", ":")))
        return 0 if all(c["matches_expected"] is True for c in cases) else 1
    except Exception:
        print("HTTP evaluation failed; private details were withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
