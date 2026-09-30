"""Small standard-library web server for the operator pages and local API."""

from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import unquote, urlparse

from tcp_v2_db import DatabaseApiClient, DatabaseApiError
from tcp_v2_run import ProductionRunController, RunError


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _handler_class(
    database: DatabaseApiClient,
    run_controller: ProductionRunController,
    static_root: Path,
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler for the operator UI and current production run."""

    static_root = static_root.resolve()

    class TrayWebHandler(BaseHTTPRequestHandler):
        server_version = "TrayPackingPython/3"

        def log_message(self, format: str, *args: object) -> None:
            logging.info("HTTP %s - %s", self.address_string(), format % args)

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 65_536:
                raise ValueError("Request body is too large")
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def _serve_static_file(self, request_path: str) -> None:
            relative_path = Path(unquote(request_path).lstrip("/"))
            candidate = (static_root / relative_path).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not candidate.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
            path = urlparse(self.path).path
            if path == "/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/Production_Select.html")
                self.end_headers()
            elif path == "/Log_In.html":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/Production_Select.html")
                self.end_headers()
            elif path == "/Register.html":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/Register_Part.html")
                self.end_headers()
            elif path == "/Running.html":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/Production_Run.html")
                self.end_headers()
            elif path == "/health":
                self._send_json(HTTPStatus.OK, {"ok": True})
            elif path == "/api/parts":
                try:
                    self._send_json(HTTPStatus.OK, {"parts": database.list_parts()})
                except DatabaseApiError as error:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            elif path == "/api/run-summary":
                try:
                    self._send_json(HTTPStatus.OK, run_controller.summary())
                except DatabaseApiError as error:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            else:
                self._serve_static_file(path)

        def do_POST(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
            path = urlparse(self.path).path
            try:
                if path == "/api/run/start":
                    data = self._read_json()
                    run = run_controller.start_run(
                        str(data.get("partNumber") or ""),
                        str(data.get("operatorName") or ""),
                    )
                    self._send_json(
                        HTTPStatus.CREATED,
                        {
                            "message": "Production run started. PLC M7/M8 results will be recorded with this part number and operator.",
                            "run": run,
                        },
                    )
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})
            except (ValueError, RunError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except DatabaseApiError as error:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            except Exception as error:  # The client must receive JSON, not an HTML traceback.
                logging.exception("Unhandled API error for %s", path)
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    return TrayWebHandler


class OperatorWebServer:
    """Host the operator HTML pages and same-origin run-selection API."""

    def __init__(
        self,
        host: str,
        port: int,
        static_root: Path,
        database: DatabaseApiClient,
        run_controller: ProductionRunController,
    ) -> None:
        if not static_root.is_dir():
            raise RuntimeError(f"WEB_ROOT does not exist or is not a directory: {static_root}")
        self._server = ThreadingHTTPServer(
            (host, port), _handler_class(database, run_controller, static_root)
        )
        self._thread = Thread(target=self._server.serve_forever, name="operator-web", daemon=True)
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True
        host, port = self._server.server_address[:2]
        logging.info("Operator web/API server listening at http://%s:%s/", host, port)

    def stop(self) -> None:
        if self._started:
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()
