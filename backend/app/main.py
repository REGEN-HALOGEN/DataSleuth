"""Local development API foundation."""

from contextlib import asynccontextmanager
import logging
import secrets
from threading import BoundedSemaphore

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.documents import router as documents_router
from app.storage.supabase import PrivateBucket
from app.scanners.readers import MAX_INPUT_BYTES
from app.api.auth import router as auth_router
from app.api.findings import router as findings_router
from app.api.overview import router as overview_router
from app.api.reports import router as reports_router
from app.api.scans import router as scans_router
from app.api.sources import router as sources_router
from app.core.auth import password_hasher
from app.core.config import load_config, organisation_roots
from app.core.logging import configure_logging
from app.core.redis_client import create_redis
from app.db.session import check_schema, create_database, expected_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO")
    logger = logging.getLogger("datasleuth")
    engine = redis = None
    try:
        try:
            config = load_config()
            configure_logging(config["LOG_LEVEL"])
            hosted = config["DATASLEUTH_MODE"] == "hosted"
            engine, sessions = create_database(config["DATABASE_URL"], hosted=hosted)
            redis = create_redis(config["REDIS_URL"])
            app.state.schema_heads = expected_schema() if hosted else None
            app.state.engine = engine
            app.state.sessions = sessions
            app.state.bucket = PrivateBucket.from_config(config)
            app.state.upload_slots = BoundedSemaphore(2)
            app.state.upload_limit = min(
                MAX_INPUT_BYTES, int(config["MAX_FILE_SIZE_BYTES"])
            )
            app.state.parser_timeout = int(config["MAX_PROCESSING_SECONDS_PER_FILE"])
            app.state.scan_roots = organisation_roots(config)
            app.state.redis = redis
            app.state.login_limit_key = config["APPLICATION_SECRET"].encode("utf-8")
            app.state.browser_origins = {config["BROWSER_ORIGIN"]}
            app.state.secure_cookies = config["BROWSER_ORIGIN"].startswith("https://")
            app.state.dummy_password_hash = password_hasher.hash(secrets.token_hex(32))
        except Exception:
            logger.error("startup_failed")
            raise RuntimeError(
                "DataSleuth startup failed. Check service configuration."
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
app.include_router(documents_router)
app.include_router(sources_router)
app.include_router(scans_router)
app.include_router(findings_router)
app.include_router(overview_router)
app.include_router(reports_router)


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
            if app.state.schema_heads is not None:
                check_schema(connection, app.state.schema_heads)
        app.state.redis.ping()
    except Exception:
        logging.getLogger("datasleuth").warning("dependency_unavailable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
