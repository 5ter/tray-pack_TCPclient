"""Start the tray-inspection client version 2.

Read README_tcpClient_v2.md first. This file intentionally contains only the
startup flow; each technical responsibility lives in a small companion module.
"""

import logging
import signal
import sys

from tcp_v2_config import BASE_DIR, Settings
from tcp_v2_db import DatabaseApiClient
from tcp_v2_job import JobController
from tcp_v2_printer import SatoPrinter
from tcp_v2_service import TrayInspectionService
from tcp_v2_web import OperatorWebServer


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(BASE_DIR / "tcp_client_v2.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> int:
    configure_logging()
    settings = Settings()
    jobs = JobController(settings, DatabaseApiClient(settings), SatoPrinter(settings))
    web_server = OperatorWebServer(settings.web_host, settings.web_port, settings.web_root, jobs)
    service = TrayInspectionService(settings, event_handler=jobs.handle_inspection_event)
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)

    try:
        web_server.start()
        service.run()
    except KeyboardInterrupt:
        service.stop()
    except Exception:
        logging.exception("Unhandled fatal error")
        return 1
    finally:
        web_server.stop()
        service.close()
        logging.info("Tray inspection client stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
