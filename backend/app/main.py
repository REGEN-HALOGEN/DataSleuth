"""Local development API foundation."""

from fastapi import FastAPI

app = FastAPI(title="DataSleuth", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return process health without revealing configuration."""
    return {"status": "ok"}
