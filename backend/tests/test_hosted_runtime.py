"""Hosted settings must preserve transport, role and filesystem boundaries."""

import pytest

from app.core.config import database_url, load_config, organisation_roots
from app.core.redis_client import create_redis
from app.db.session import check_schema, create_database, expected_schema

RUNTIME = (
    "postgresql+psycopg://runtime:synthetic@db.example.invalid/db?sslmode=verify-full"
)


@pytest.fixture
def hosted(monkeypatch):
    values = {
        "DATASLEUTH_MODE": "hosted",
        "DATABASE_URL": RUNTIME,
        "MIGRATION_DATABASE_URL": RUNTIME.replace("runtime:", "migrator:"),
        "POSTGRES_PASSWORD": "",
        "REDIS_PASSWORD": "",
        "REDIS_URL": "rediss://default:synthetic@redis.example.invalid:6379",
        "BROWSER_ORIGIN": "https://inventory.example.invalid",
        "APPLICATION_SECRET": "synthetic-application-secret-for-tests",
        "HMAC_KEY": "synthetic-fingerprint-secret-for-tests",
        "HMAC_KEY_VERSION": "1",
        "ALLOWED_SCAN_ROOTS": "[]",
        "ORGANISATION_SCAN_ROOTS": "{}",
        "MAX_FILE_SIZE_BYTES": "10485760",
        "MAX_SCAN_DEPTH": "10",
        "MAX_FILES_PER_SCAN": "10000",
        "MAX_PROCESSING_SECONDS_PER_FILE": "30",
        "LOG_LEVEL": "INFO",
        "SUPABASE_STORAGE_URL": "https://example.supabase.co/storage/v1",
        "SUPABASE_STORAGE_BUCKET": "private",
        "SUPABASE_STORAGE_KEY": "sb_secret_synthetic",
        "UPLOAD_INTEGRITY_KEY": "synthetic-document-integrity-secret-for-tests",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_hosted_service_secrets_and_pool_limits(hosted):
    hosted.delenv("HMAC_KEY")
    config = load_config()
    assert organisation_roots(config) == {}
    hosted.setenv("HMAC_KEY", "synthetic-fingerprint-secret-for-tests")
    hosted.delenv("BROWSER_ORIGIN")
    hosted.delenv("APPLICATION_SECRET")
    load_config(service="worker")
    for worker, limit in ((False, 3), (True, 2)):
        engine, _ = create_database(RUNTIME, hosted=True, worker=worker)
        try:
            assert engine.pool.size() == limit
            assert engine.pool.timeout() == 3
        finally:
            engine.dispose()
    with create_redis(config["REDIS_URL"]) as redis:
        assert redis.connection_pool.connection_kwargs["ssl_check_hostname"] is True


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("BROWSER_ORIGIN", "http://inventory.example.invalid"),
        ("BROWSER_ORIGIN", "https://inventory.example.invalid/path"),
        ("DATABASE_URL", RUNTIME.replace("verify-full", "require")),
        ("DATABASE_URL", RUNTIME.replace("/db", ":6543/db")),
        ("REDIS_URL", "redis://default:synthetic@redis.example.invalid"),
        ("REDIS_URL", "redis://red-abc123:6379"),
        ("REDIS_URL", "rediss://default:synthetic@red-abc123?ssl_cert_reqs=none"),
        ("ALLOWED_SCAN_ROOTS", '["/tmp"]'),
        ("SUPABASE_STORAGE_URL", "http://127.0.0.1:25000"),
    ],
)
def test_insecure_hosted_configuration_fails_closed(hosted, key, value):
    hosted.setenv(key, value)
    with pytest.raises(ValueError, match="Invalid configuration") as failure:
        load_config()
    assert "synthetic" not in str(failure.value)


def test_database_only_migration_configuration(hosted):
    for key in (
        "REDIS_URL",
        "APPLICATION_SECRET",
        "HMAC_KEY",
        "SUPABASE_STORAGE_KEY",
        "DATABASE_URL",
    ):
        hosted.delenv(key)
    assert database_url(migration=True) == RUNTIME.replace("runtime:", "migrator:")
    hosted.delenv("MIGRATION_DATABASE_URL")
    with pytest.raises(ValueError, match="Invalid database configuration"):
        database_url(migration=True)


def test_schema_gate_detects_an_empty_database(services):
    engine, _ = create_database(database_url(), hosted=True)
    try:
        with engine.connect() as connection:
            check_schema(connection, expected_schema())
        with engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL search_path TO pg_catalog")
            with pytest.raises(RuntimeError, match="schema revision"):
                check_schema(connection, expected_schema())
    finally:
        engine.dispose()
