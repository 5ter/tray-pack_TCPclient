"""Start the simplified tray-inspection client.

Read README_production_v3.md first. This file intentionally contains only the
startup flow; each technical responsibility lives in a small companion module.
"""

import logging
import signal
import sys

from tcp_v2_config import BASE_DIR, Settings
from tcp_v2_camera_server import CameraModeTcpServer
from tcp_v2_db import DatabaseApiClient
from tcp_v2_outbox import LocalResultOutbox
from tcp_v2_plc_status import PlcConnectionStatus
from tcp_v2_run import ProductionRunController
from tcp_v2_service import TrayInspectionService
from tcp_v2_sender import ResultSubmitter
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
    database = DatabaseApiClient(settings)
    outbox = LocalResultOutbox(settings.result_outbox_path)
    submitter = ResultSubmitter(
        database,
        outbox,
        flush_interval_seconds=settings.result_batch_interval_seconds,
        batch_size=settings.result_batch_size,
    )
    runs = ProductionRunController(settings, database, submitter)
    plc_status = PlcConnectionStatus()
    web_server = OperatorWebServer(
        settings.web_host, settings.web_port, settings.web_root, database, runs, plc_status
    )
    camera_server = CameraModeTcpServer(settings.camera_tcp_host, settings.camera_tcp_port)
    service = TrayInspectionService(
        settings,
        event_handler=runs.handle_inspection_event,
        camera_mode_handler=camera_server.update_mode,
        plc_status=plc_status,
    )
    signal.signal(signal.SIGINT, service.stop)
    signal.signal(signal.SIGTERM, service.stop)

    try:
        web_server.start()
        camera_server.start()
        service.run()
    except KeyboardInterrupt:
        service.stop()
    except Exception:
        logging.exception("Unhandled fatal error")
        return 1
    finally:
        camera_server.stop()
        web_server.stop()
        service.close()
        submitter.close()
        outbox.close()
        logging.info("Tray inspection client stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
