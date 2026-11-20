import pytest

from app.core.config import load_config


def test_missing_secret_fails_without_disclosing_it(monkeypatch):
    monkeypatch.setenv("HMAC_KEY", "")
    with pytest.raises(ValueError, match="Missing or placeholder"):
        load_config()


def test_remote_database_rejected_without_echoing_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:private@remote/db")
    with pytest.raises(ValueError) as error:
        load_config()
    assert "private" not in str(error.value)


def test_invalid_scan_roots_rejected(monkeypatch):
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", '["relative/path"]')
    with pytest.raises(ValueError):
        load_config()
