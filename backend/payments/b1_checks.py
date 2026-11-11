"""Opt-in, read-only deployment checks. Never log credentials or provider bodies."""
import logging
import os
from threading import Thread

from backend.payments.sandbox_auth import check_sandbox_auth

logger = logging.getLogger("uvicorn.error")


def check_database(database_url: str) -> None:
    if not database_url:
        raise ValueError("DATABASE_URL is not configured")
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Unexpected database response")


def run_checks() -> None:
    try:
        check_database(os.getenv("DATABASE_URL", ""))
    except Exception:
        # Driver errors can contain connection details, so never print exceptions.
        logger.error("B1 database check FAILED; verify DATABASE_URL, database status, network access and credentials.")
    else:
        logger.info("B1 database check PASSED (SELECT 1).")

    try:
        check_sandbox_auth(os.getenv("PAYPAL_CLIENT_ID", ""), os.getenv("PAYPAL_CLIENT_SECRET", ""))
    except Exception:
        # Do not log provider response bodies, exception details, or tokens.
        logger.error("B1 PayPal Sandbox OAuth check FAILED; verify Sandbox credentials and outbound access.")
    else:
        logger.info("B1 PayPal Sandbox OAuth check PASSED.")


def start_checks_if_enabled() -> None:
    if os.getenv("RUN_B1_CHECKS", "").lower() == "true":
        Thread(target=run_checks, name="b1-checks", daemon=True).start()
