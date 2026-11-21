"""Run the local scan worker from WSL/Linux."""

from datetime import datetime, timezone
import logging
import os
import signal
import time

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import load_config, organisation_roots
from app.core.logging import configure_logging
from app.core.redis_client import create_redis
from app.db.session import check_schema, create_database, expected_schema
from app.storage.retention import purge_due
from app.storage.supabase import PrivateBucket
from app.scanners.pipeline import lease_duration, run_claim
from app.workers.queue import WAKE_KEY, ScanError, claim_next, leased_job

POLL_SECONDS = 2


def run_worker(sessions, redis, config) -> None:
    logger = logging.getLogger("datasleuth")
    active = None
    grants = organisation_roots(config)
    bucket = PrivateBucket.from_config(config)
    next_cleanup = 0.0
    try:
        while True:
            try:
                if bucket and time.monotonic() >= next_cleanup:
                    next_cleanup = time.monotonic() + 15
                    purge_due(sessions, bucket)
                active = claim_next(
                    sessions,
                    lease_duration(config),
                    organisation_ids=tuple(grants),
                    namespace=bucket.namespace if bucket else None,
                )
                if active is not None:
                    run_claim(
                        sessions,
                        config,
                        active,
                        roots=grants.get(active.organisation_id, ()),
                    )
                    active = None
                    continue
            except (ScanError, SQLAlchemyError):
                logger.warning("scan_worker_storage_unavailable")
            try:
                redis.blpop(WAKE_KEY, timeout=POLL_SECONDS)
            except RedisError:
                time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        if active is not None:
            try:
                with sessions.begin() as db:
                    job = leased_job(db, active)
                    if job is not None:
                        job.lease_until = datetime.now(timezone.utc)
            except SQLAlchemyError:
                logger.warning("scan_worker_storage_unavailable")


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main() -> None:
    configure_logging("INFO")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise SystemExit("The scan worker requires WSL or Linux.")
    signal.signal(signal.SIGTERM, interrupt)
    engine = redis = None
    try:
        config = load_config(service="worker")
        configure_logging(config["LOG_LEVEL"])
        hosted = config["DATASLEUTH_MODE"] == "hosted"
        engine, sessions = create_database(
            config["DATABASE_URL"], hosted=hosted, worker=True
        )
        if hosted:
            with engine.connect() as connection:
                check_schema(connection, expected_schema())
        redis = create_redis(config["REDIS_URL"], worker=True)
        logging.getLogger("datasleuth").info("scan_worker_started")
        run_worker(sessions, redis, config)
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger("datasleuth").error("scan_worker_stopped_unexpectedly")
        raise SystemExit("The scan worker stopped unexpectedly.") from None
    finally:
        if redis is not None:
            redis.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
