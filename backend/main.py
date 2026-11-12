"""FastAPI entry point; integration and deployment are owned by member B."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from backend.payments.b1_checks import start_checks_if_enabled
from backend.payments.harness import router as payment_router, enabled
from backend.payments.capture import router as capture_router
from backend.session import COOKIE, configured_secret, new_cookie, session_for_cookie


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("B4_ENABLED", "").lower() == "true" and not getattr(_app.state, "b4_router_mounted", False):
        configured_secret()
        from backend.integration import create_negotiation_router
        _app.include_router(create_negotiation_router())
        _app.state.b4_router_mounted = True
    if os.getenv("B2_RUN_MIGRATIONS", "").lower() == "true":
        from backend.domain.database import DomainDatabase
        from backend.domain.migrate import apply_migrations
        from backend.payments.migrate import apply
        try:
            apply_migrations(DomainDatabase.from_environment())
            apply(os.getenv("DATABASE_URL", ""))
        except Exception:
            logging.getLogger("uvicorn.error").error("B2 migrations failed; inspect database access and migration status.")
            raise RuntimeError("B2 migrations failed") from None
        logging.getLogger("uvicorn.error").info("B2 domain and payment migrations completed.")
    seed_scenario = os.getenv("B4_SEED_SCENARIO", "")
    if seed_scenario:
        if os.getenv("B4_ENABLED", "").lower() != "true" or os.getenv("B4_ACKNOWLEDGE_SYNTHETIC_STOCK", "").lower() != "true":
            raise RuntimeError("Synthetic stock seed requires B4 and explicit acknowledgement")
        from backend.domain.database import DomainDatabase
        from backend.domain.seed import seed_fixture
        try:
            inserted = seed_fixture(DomainDatabase.from_environment(), seed_scenario)
        except Exception:
            logging.getLogger("uvicorn.error").error("B4 synthetic stock seed failed; check migrations and existing stock.")
            raise RuntimeError("B4 synthetic stock seed failed") from None
        logging.getLogger("uvicorn.error").info("B4 synthetic stock seed completed: %s new batches.", inserted)
    start_checks_if_enabled()
    yield


_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"


async def integrated_session(request, call_next):
    if os.getenv("B4_ENABLED", "").lower() != "true":
        return await call_next(request)
    secret = configured_secret()
    cookie = request.cookies.get(COOKIE, "")
    session_id = session_for_cookie(cookie, secret)
    issued = session_id is None
    if issued:
        cookie = new_cookie(secret)
        session_id = session_for_cookie(cookie, secret)
    request.state.session_id = session_id
    response = await call_next(request)
    if issued:
        response.set_cookie(COOKIE, cookie, httponly=True, secure=bool(os.getenv("RENDER")), samesite="lax", path="/")
    return response


def health() -> dict[str, str]:
    return {"status": "ok"}


def frontend():
    index = _frontend_dist / "index.html"
    if os.getenv("B4_ENABLED", "").lower() != "true" or not index.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(index)


def test_checkout():
    if not enabled():
        raise HTTPException(404, "Not found")
    return Path(__file__).with_name("payments").joinpath("harness.html").read_text(encoding="utf-8-sig")


def test_checkout_script():
    if not enabled():
        raise HTTPException(404, "Not found")
    content = Path(__file__).with_name("payments").joinpath("harness.js").read_text(encoding="utf-8-sig")
    return Response(content, media_type="application/javascript")


def create_app() -> FastAPI:
    """A fresh host for startup/integration tests; the deployment entry point stays app."""
    application = FastAPI(title="AgentNegotiate", lifespan=lifespan)
    application.include_router(payment_router)
    application.include_router(capture_router)
    application.mount("/assets", StaticFiles(directory=_frontend_dist / "assets", check_dir=False), name="frontend-assets")
    application.middleware("http")(integrated_session)
    application.add_api_route("/health", health, methods=["GET"])
    application.add_api_route("/", frontend, methods=["GET"], include_in_schema=False)
    application.add_api_route("/test-checkout", test_checkout, methods=["GET"], response_class=HTMLResponse)
    application.add_api_route("/test-checkout.js", test_checkout_script, methods=["GET"])
    return application


app = create_app()
