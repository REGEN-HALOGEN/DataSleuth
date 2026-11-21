"""Configuration for opt-in disposable service tests."""

import os

import pytest


@pytest.fixture(scope="module")
def services():
    names = ("DATABASE_URL", "POSTGRES_PASSWORD", "REDIS_URL", "REDIS_PASSWORD")
    settings = {name: os.getenv(f"DATASLEUTH_TEST_{name}") for name in names}
    if not all(settings.values()):
        pytest.skip(
            "Set DATASLEUTH_TEST_* for disposable PostgreSQL and Redis services."
        )
    if "datasleuth_" not in settings["DATABASE_URL"].rsplit("/", 1)[-1]:
        pytest.fail("Select a disposable database with a datasleuth_ prefix.")
    with pytest.MonkeyPatch.context() as patch:
        for name, value in settings.items():
            patch.setenv(name, value)
        for name in (
            "UPLOAD_INTEGRITY_KEY",
            "SUPABASE_STORAGE_URL",
            "SUPABASE_STORAGE_KEY",
            "SUPABASE_STORAGE_BUCKET",
        ):
            patch.setenv(name, "")
        patch.setenv("BROWSER_ORIGIN", "http://127.0.0.1:5173")
        yield
