"""FastAPI entry point; integration and deployment are owned by member B."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.payments.b1_checks import start_checks_if_enabled


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_checks_if_enabled()
    yield


app = FastAPI(title="AgentNegotiate", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
