"""Explicit server-side Gemini settings; never load credentials at import time."""

from collections.abc import Mapping
import os
from pathlib import Path
import re
from typing import Annotated, Literal, Self

from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationError, field_validator

from .contracts import Contract


class ModelConfigurationError(RuntimeError):
    """Only static messages containing configuration names, never their values."""


class GeminiSettings(Contract):
    api_key: SecretStr = Field(exclude=True, repr=False)
    model: Annotated[str, Field(strict=True, pattern=r"^gemini-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")]
    timeout_ms: Annotated[int, Field(strict=True, ge=1000, le=60000)] = 30000
    max_output_tokens: Annotated[int, Field(strict=True, ge=128, le=4096)] = 2048
    thinking_level: Literal["low", "medium", "high"] | None = None

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if (
            not 1 <= len(raw) <= 512
            or not raw.isascii()
            or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in raw)
            or raw.lower() in {"changeme", "replace_me", "your_gemini_api_key"}
            or "${" in raw
        ):
            raise ValueError("GEMINI_API_KEY must contain a configured server-side key")
        return value

    @classmethod
    def from_environment(
        cls, *, env_file: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> Self:
        """Process values win, even if empty. No discovery or os.environ mutation.

        A file is read only when explicitly supplied. Dotenv interpolation is
        disabled so unrelated environment secrets cannot be substituted.
        """
        source = os.environ if environ is None else environ
        names = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_MS", "GEMINI_MAX_OUTPUT_TOKENS", "GEMINI_THINKING_LEVEL")
        file_values: dict[str, str | None] = {}
        if env_file is not None:
            try:
                with env_file.open(encoding="utf-8") as stream:
                    file_values = dict(dotenv_values(stream=stream, interpolate=False))
            except (OSError, UnicodeError):
                raise ModelConfigurationError("Cannot read the specified Gemini environment file.") from None
        values = {name: source[name] if name in source else file_values.get(name) for name in names}
        if not values["GEMINI_API_KEY"]:
            raise ModelConfigurationError("GEMINI_API_KEY is required; configure it locally, never in chat.")
        if not values["GEMINI_MODEL"]:
            raise ModelConfigurationError("GEMINI_MODEL is required; no model is selected automatically.")
        data: dict[str, object] = {"api_key": values["GEMINI_API_KEY"], "model": values["GEMINI_MODEL"]}
        if values["GEMINI_THINKING_LEVEL"] is not None:
            data["thinking_level"] = values["GEMINI_THINKING_LEVEL"]
        for name, field in (("GEMINI_TIMEOUT_MS", "timeout_ms"), ("GEMINI_MAX_OUTPUT_TOKENS", "max_output_tokens")):
            raw = values[name]
            if raw is not None:
                if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,6}", raw):
                    raise ModelConfigurationError(f"{name} must be an integer within the documented limits.")
                data[field] = int(raw)
        try:
            return cls.model_validate(data)
        except ValidationError:
            raise ModelConfigurationError("Gemini configuration is invalid; check key, model ID, timeout, token limits, and thinking level.") from None
