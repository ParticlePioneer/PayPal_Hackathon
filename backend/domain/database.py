"""Domain-only PostgreSQL configuration and transaction boundary."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
from pydantic import SecretStr


_ERRORS = {
    "invalid_input": (422, "Invalid domain input."),
    "invalid_agreement": (422, "A validated mutual agreement is required."),
    "not_found": (404, "Quote or operation not found."),
    "expired": (410, "The quote has expired."),
    "stock_conflict": (409, "Stock is unavailable or already held."),
    "operation_conflict": (409, "The operation conflicts with existing quote state."),
    "idempotency_conflict": (409, "The request identifier was already used for different terms."),
    "migration_conflict": (409, "An applied domain migration has changed."),
    "storage_unavailable": (503, "Domain storage is unavailable; private database details were withheld."),
}


class DomainError(RuntimeError):
    def __init__(self, code):
        self.code = code
        self.status_code, message = _ERRORS[code]
        super().__init__(message)


class DomainDatabase:
    """Fresh connection per operation; database URL is never logged or exposed."""

    def __init__(self, dsn: str, *, schema: str = "public"):
        if not isinstance(dsn, str) or not dsn or not isinstance(schema, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
            raise DomainError("invalid_input")
        try:
            parsed = urlsplit(dsn)
            if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
                raise ValueError("An explicit PostgreSQL URL and database are required")
            parsed.port  # Reject malformed ports without exposing the URL.
        except ValueError:
            raise DomainError("invalid_input") from None
        self._dsn = SecretStr(dsn)
        self.schema = schema

    @classmethod
    def from_environment(cls, *, env_file: Path | None = None):
        values = {}
        if env_file is not None:
            try:
                with env_file.open(encoding="utf-8") as stream:
                    values = dotenv_values(stream=stream, interpolate=False)
            except (OSError, UnicodeError):
                raise DomainError("invalid_input") from None
        return cls(os.environ.get("DATABASE_URL", values.get("DATABASE_URL")) or "")

    def connect(self):
        return psycopg.connect(
            self._dsn.get_secret_value(), connect_timeout=5, row_factory=dict_row,
            options=f"-c search_path={self.schema} -c timezone=UTC -c statement_timeout=10000 -c lock_timeout=5000",
        )

    @contextmanager
    def transaction(self):
        try:
            with self.connect() as connection:
                yield connection
        except psycopg.Error:
            raise DomainError("storage_unavailable") from None
