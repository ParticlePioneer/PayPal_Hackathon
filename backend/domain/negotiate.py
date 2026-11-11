"""A2 terminal runner. Explicit mock/live mode; no quote or payment capability."""

import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from .model_client import GeminiActionClient, MAX_INPUT_BYTES
from .model_config import GeminiSettings, ModelConfigurationError
from .negotiation import NegotiationLimits, NegotiationScenario, run_negotiation
from .negotiation_fixtures import FixtureAgents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Two-agent terminal runner; agreed terms are unreserved and cannot be checked out.")
    parser.add_argument("--mode", choices=("mock", "live"), required=True)
    parser.add_argument("--input", type=Path, required=True, help="Private server-side NegotiationScenario JSON, including an explicit seller floor.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--turn-timeout-ms", type=int, default=30000)
    parser.add_argument("--total-timeout-ms", type=int, default=120000)
    args = parser.parse_args(argv)
    try:
        limits = NegotiationLimits(max_turns=args.max_turns, turn_timeout_ms=args.turn_timeout_ms, total_timeout_ms=args.total_timeout_ms)
        with args.input.open("rb") as stream:
            payload = stream.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise ValueError("Input too large")
        scenario = NegotiationScenario.model_validate_json(payload)
        if args.mode == "mock":
            source = FixtureAgents()
        else:
            env_file = args.env_file
            if env_file is None:
                candidate = Path(__file__).resolve().parents[2] / ".env"
                env_file = candidate if candidate.exists() else None
            source = GeminiActionClient(GeminiSettings.from_environment(env_file=env_file))
        outcome = run_negotiation(scenario, source, limits)
        print(json.dumps({"mode": args.mode, "simulated": args.mode == "mock", "result": outcome.model_dump(mode="json")}, separators=(",", ":")))
        return 0 if outcome.status in {"agreed", "no_deal"} else 1
    except ModelConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, ValidationError):
        print("Negotiation input or limits are invalid; private details were withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
