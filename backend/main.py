"""FastAPI entry point; integration and deployment are owned by member B."""

from fastapi import FastAPI

app = FastAPI(title="AgentNegotiate")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
