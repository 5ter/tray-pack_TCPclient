"""TCP receiver for tray-packing result messages.

Expected input, one JSON object per line:
    {"id": "TRAY-PACK-01", "status": "OK"}
"""

import json
import logging
import socketserver


HOST = "0.0.0.0"
PORT = 3333
VALID_STATUSES = {"OK", "NG"}

logging.basicConfig(
    filename="tray_result_server.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def process_result(machine_id, status, client_address):
    """Handle one validated result message.

    Add database writes, PLC acknowledgements, or other downstream handling here.
    """
    message = f"Result received: id={machine_id}, status={status}"
    print(message)
    logging.info("%s from %s:%s", message, *client_address)


class TrayResultHandler(socketserver.StreamRequestHandler):
    """Read and process newline-delimited JSON messages from one client."""

    def handle(self):
        logging.info("Client connected: %s:%s", *self.client_address)

        for raw_message in self.rfile:
            try:
                message = json.loads(raw_message.decode("utf-8"))
                machine_id = message["id"]
                status = message["status"]

                if not isinstance(machine_id, str) or not machine_id:
                    raise ValueError("'id' must be a non-empty string")
                if status not in VALID_STATUSES:
                    raise ValueError("'status' must be either 'OK' or 'NG'")

                process_result(machine_id, status, self.client_address)
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as error:
                logging.warning(
                    "Invalid message from %s:%s: %s",
                    *self.client_address,
                    error,
                )

        logging.info("Client disconnected: %s:%s", *self.client_address)


class ThreadedTrayResultServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    with ThreadedTrayResultServer((HOST, PORT), TrayResultHandler) as server:
        print(f"Tray result server listening on {HOST}:{PORT}")
        logging.info("Tray result server listening on %s:%s", HOST, PORT)
        server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTray result server stopped")
