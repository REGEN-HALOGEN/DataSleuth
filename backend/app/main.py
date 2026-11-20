"""Local development API foundation."""

from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.findings import router as findings_router
from app.api.overview import router as overview_router
from app.api.scans import router as scans_router
from app.api.sources import router as sources_router
from app.core.auth import password_hasher
from app.core.config import load_config
from app.core.logging import configure_logging
from app.db.session import create_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO")
    logger = logging.getLogger("datasleuth")
    engine = redis = None
    try:
        try:
            config = load_config()
            configure_logging(config["LOG_LEVEL"])
            engine, sessions = create_database(config["DATABASE_URL"])
            redis = Redis.from_url(
                config["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2
            )
            app.state.engine = engine
            app.state.sessions = sessions
            app.state.scan_roots = tuple(
                Path(root) for root in json.loads(config["ALLOWED_SCAN_ROOTS"])
            )
            app.state.redis = redis
            app.state.login_limit_key = config["APPLICATION_SECRET"].encode("utf-8")
            app.state.browser_origins = {config["BROWSER_ORIGIN"]}
            app.state.secure_cookies = config["BROWSER_ORIGIN"].startswith("https://")
            app.state.dummy_password_hash = password_hasher.hash(secrets.token_hex(32))
        except Exception:
            logger.error("startup_failed")
            raise RuntimeError(
                "DataSleuth startup failed. Check local configuration."
            ) from None
        logger.info("service_started")
        yield
        logger.info("service_stopped")
    finally:
        try:
            if redis is not None:
                redis.close()
        finally:
            if engine is not None:
                engine.dispose()


app = FastAPI(title="DataSleuth", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(sources_router)
app.include_router(scans_router)
app.include_router(findings_router)
app.include_router(overview_router)


@app.middleware("http")
async def prevent_private_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


@app.get("/health")
def health() -> dict[str, str]:
    """Return process health without revealing configuration."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    """Report dependency availability without returning exception details."""
    try:
        with app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        app.state.redis.ping()
    except Exception:
        logging.getLogger("datasleuth").warning("dependency_unavailable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
