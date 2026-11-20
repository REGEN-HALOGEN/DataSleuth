import json
import logging

from app.core.logging import SafeJsonFormatter


def test_unknown_message_args_extras_and_traceback_are_never_serialized():
    secret = "synthetic-secret-and-personal-value@example.invalid"
    try:
        raise ValueError(secret)
    except ValueError:
        import sys

        record = logging.LogRecord(
            "untrusted",
            logging.ERROR,
            secret,
            1,
            "password %s",
            (secret,),
            sys.exc_info(),
        )
    record.token = secret
    output = SafeJsonFormatter().format(record)
    assert secret not in output
    assert json.loads(output)["event"] == "event_redacted"


def test_only_static_allowlisted_event_is_emitted():
    record = logging.LogRecord("test", logging.INFO, "", 0, "service_started", (), None)
    record.password = "synthetic-password"
    output = SafeJsonFormatter().format(record)
    assert json.loads(output)["event"] == "service_started"
    assert "synthetic-password" not in output


def test_startup_error_does_not_log_exception_details():
    import subprocess
    import sys

    script = """
from fastapi.testclient import TestClient
import app.main

def fail():
    raise ValueError("synthetic-startup-secret")

app.main.load_config = fail
try:
    with TestClient(app.main.app):
        raise AssertionError("startup should fail")
except RuntimeError as failure:
    assert "synthetic-startup-secret" not in str(failure)
    assert failure.__suppress_context__
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert "synthetic-startup-secret" not in result.stderr
    assert json.loads(result.stderr.strip())["event"] == "startup_failed"
