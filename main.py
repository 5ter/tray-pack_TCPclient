from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException
import time
import logging
import socket
import json

logging.basicConfig(
    filename="plc_client.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

PLC_IP = "192.168.6.6"
PLC_PORT = 502
UNIT_ID = 1
SERVER_IP = "192.168.40.29"
SERVER_PORT = 3333
SERVER_TIMEOUT = 2
MACHINE_ID = "TRAY-PACK-01"

client = ModbusTcpClient(PLC_IP, port=PLC_PORT, timeout=1)
server_socket = None

last_seen = {7: 0, 8: 0}

def process_event(label):
    print(f"Processing event: {label}")
    logging.info(f"Event: {label}")
    send_to_server(label)


def close_server_connection():
    """Close the server socket and ensure the next event reconnects."""
    global server_socket

    if server_socket is not None:
        try:
            server_socket.close()
        except OSError:
            pass
        server_socket = None


def send_to_server(label):
    """Send one newline-delimited JSON tray result to the TCP server."""
    global server_socket

    try:
        if server_socket is None:
            logging.info(f"Connecting to result server at {SERVER_IP}:{SERVER_PORT}")
            server_socket = socket.create_connection(
                (SERVER_IP, SERVER_PORT), timeout=SERVER_TIMEOUT
            )

        payload = json.dumps({"id": MACHINE_ID, "status": label}) + "\n"
        server_socket.sendall(payload.encode("utf-8"))
        logging.info(f"Sent result to server: {payload.strip()}")
    except OSError as e:
        logging.error(f"Could not send result '{label}' to server: {e}")
        close_server_connection()

def ensure_connected():
    if not client.connected:
        logging.warning("Reconnecting to PLC...")
        client.connect()

def main_loop():
    while True:
        try:
            ensure_connected()
            rr = client.read_coils(7, count=2, slave=UNIT_ID)

            if rr.isError():
                logging.error(f"Modbus error response: {rr}")
            else:
                m7, m8 = rr.bits[0], rr.bits[1]

                if m7 and not last_seen[7]:
                    process_event("OK")
                    last_seen[7] = 1
                elif not m7:
                    last_seen[7] = 0

                if m8 and not last_seen[8]:
                    process_event("NG")
                    last_seen[8] = 1
                elif not m8:
                    last_seen[8] = 0

        except (ConnectionException, ModbusException) as e:
            logging.error(f"Communication error: {e}")
            client.close()
            time.sleep(1)

        time.sleep(0.2)

if __name__ == "__main__":
    try: 
        while True:
            try:
                main_loop()
            except Exception as e:
                # catch anything truly unexpected so the process never dies
                logging.critical(f"Unhandled exception, restarting loop: {e}", exc_info=True)
                time.sleep(2)
    finally:
        close_server_connection()
        client.close()
