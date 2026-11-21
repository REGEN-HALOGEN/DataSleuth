"""Start the local API with redacted logging before loading the application."""

import logging
import os

from app.core.config import deployment_mode

from app.core.logging import configure_logging


def main() -> None:
    configure_logging("INFO")
    try:
        import uvicorn

        hosted = deployment_mode() == "hosted"
        port = int(os.environ["PORT"]) if hosted else 8000
        if not 1 <= port <= 65535:
            raise ValueError
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0" if hosted else "127.0.0.1",
            port=port,
            workers=1,
            timeout_graceful_shutdown=20,
            log_config=None,
            access_log=False,
            proxy_headers=False,
        )
    except Exception:
        logging.getLogger("datasleuth").error("startup_failed")
        raise SystemExit("DataSleuth could not start.") from None


if __name__ == "__main__":
    main()
