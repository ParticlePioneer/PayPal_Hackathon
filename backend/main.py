"""FastAPI entry point; integration and deployment are owned by member B."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from backend.payments.b1_checks import start_checks_if_enabled
from backend.payments.harness import router as payment_router, enabled
from backend.payments.capture import router as capture_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    start_checks_if_enabled()
    yield


app = FastAPI(title="AgentNegotiate", lifespan=lifespan)
app.include_router(payment_router)
app.include_router(capture_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/test-checkout", response_class=HTMLResponse)
def test_checkout():
    if not enabled():
        raise HTTPException(404, "Not found")
    return Path(__file__).with_name("payments").joinpath("harness.html").read_text(encoding="utf-8-sig")


@app.get("/test-checkout.js")
def test_checkout_script():
    if not enabled():
        raise HTTPException(404, "Not found")
    content = Path(__file__).with_name("payments").joinpath("harness.js").read_text(encoding="utf-8-sig")
    return Response(content, media_type="application/javascript")
