"""One real model call, or an offline configuration check; no negotiation run."""

import argparse
from pathlib import Path
import sys

from pydantic import ValidationError

from .contracts import BuyerAgentInput, SellerAgentInput, SharedNegotiationContext
from .fixtures import buyer_fixture
from .model_client import GeminiActionClient, ModelCallError, MAX_INPUT_BYTES
from .model_config import GeminiSettings, ModelConfigurationError


def _agent_input(role: str, input_file: Path | None):
    if input_file is None:
        if role != "buyer":
            raise ModelConfigurationError("Seller smoke requires --input with an explicit seller contract; no policy is invented.")
        buyer = buyer_fixture()
        return BuyerAgentInput(private=buyer, shared=SharedNegotiationContext(requirements=buyer.requirements))
    try:
        with input_file.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("Input too large")
        cls = BuyerAgentInput if role == "buyer" else SellerAgentInput
        return cls.model_validate_json(raw)
    except (OSError, ValueError, ValidationError):
        raise ModelConfigurationError("Cannot read a valid role-specific --input contract within the size limit.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gemini single-action smoke check; never performs negotiation or payment.")
    parser.add_argument("--env-file", type=Path, help="Explicit dotenv file; otherwise reads repository .env only if it exists.")
    parser.add_argument("--role", choices=("buyer", "seller"), default="buyer")
    parser.add_argument("--input", type=Path, help="Private JSON matching the selected role's agent-input contract.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration only; makes no provider call.")
    args = parser.parse_args(argv)
    try:
        env_file = args.env_file
        if env_file is None:
            candidate = Path(__file__).resolve().parents[2] / ".env"
            env_file = candidate if candidate.exists() else None
        settings = GeminiSettings.from_environment(env_file=env_file)
        if args.check_config:
            print(f"Gemini configuration valid: model={settings.model}. Credentials were not verified; no request sent.")
            return 0
        agent_input = _agent_input(args.role, args.input)
        client = GeminiActionClient(settings)
        action = client.generate_buyer(agent_input) if args.role == "buyer" else client.generate_seller(agent_input)
        print(f"Gemini smoke passed: model={settings.model}; role={args.role}; action={action.type}. "
              "One action parsed; no negotiation, quote, or payment performed.")
        return 0
    except (ModelConfigurationError, ModelCallError) as exc:
        print(f"Gemini smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
