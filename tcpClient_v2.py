"""Start the tray-inspection client version 2.

Read README_tcpClient_v2.md first. This file intentionally contains only the
startup flow; each technical responsibility lives in a small companion module.
"""

import logging
import signal
import sys

from tcp_v2_config import BASE_DIR, Settings
from tcp_v2_service import TrayInspectionService


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
    service = TrayInspectionService(Settings())
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)

    try:
        service.run()
    except KeyboardInterrupt:
        service.stop()
    except Exception:
        logging.exception("Unhandled fatal error")
        return 1
    finally:
        service.close()
        logging.info("Tray inspection client stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
