"""Explicit, server-side configuration for the OpenRouter model client."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from dotenv import dotenv_values


from .model_config import ModelConfigurationError


ConfigurationError = ModelConfigurationError


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str = "dots-studio/dots-3-note-preview:free"
    timeout_ms: int = 30000
    max_output_tokens: int = 4096

    @classmethod
    def from_environment(cls, *, env_file: Path | None = None, environ=None):
        path = env_file
        env = os.environ if environ is None else environ
        try:
            values = dotenv_values(path, interpolate=False) if path is not None else {}
            if path is not None and not path.is_file():
                raise OSError()
        except (OSError, UnicodeError):
            raise ConfigurationError("Cannot read the specified environment file.") from None
        def get(name, default=None):
            return env[name] if name in env else values.get(name, default)
        key = get("OPENROUTER_API_KEY")
        model = get("OPENROUTER_MODEL", cls.model)
        if not key or not key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in key) or len(key) > 512:
            raise ConfigurationError("OPENROUTER_API_KEY is required; add it locally, not in chat.")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:free", model):
            raise ConfigurationError("OPENROUTER_MODEL must be an explicit free model ID ending in :free.")
        try:
            timeout = int(get("OPENROUTER_TIMEOUT_MS", "30000"))
            tokens = int(get("OPENROUTER_MAX_OUTPUT_TOKENS", "4096"))
        except (TypeError, ValueError):
            raise ConfigurationError("Timeout and token limit must be integers.") from None
        if not 1000 <= timeout <= 60000 or not 128 <= tokens <= 4096:
            raise ConfigurationError("Timeout or token limit is outside the allowed range.")
        return cls(key, model, timeout, tokens)
