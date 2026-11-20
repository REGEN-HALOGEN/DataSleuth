"""Start the local API with redacted logging before loading the application."""

import logging

from app.core.logging import configure_logging


def main() -> None:
    configure_logging("INFO")
    try:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=8000,
            log_config=None,
            access_log=False,
            proxy_headers=False,
        )
    except Exception:
        logging.getLogger("datasleuth").error("startup_failed")
        raise SystemExit("DataSleuth could not start.") from None


if __name__ == "__main__":
    main()
