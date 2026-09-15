from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException
import time
import logging

logging.basicConfig(
    filename="plc_client.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

PLC_IP = "192.168.6.6"
PLC_PORT = 502
UNIT_ID = 1

client = ModbusTcpClient(PLC_IP, port=PLC_PORT, timeout=1)

last_seen = {7: 0, 8: 0}

def process_event(label):
    print(f"Processing event: {label}")
    logging.info(f"Event: {label}")

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
    while True:
        try:
            main_loop()
        except Exception as e:
            # catch anything truly unexpected so the process never dies
            logging.critical(f"Unhandled exception, restarting loop: {e}", exc_info=True)
            time.sleep(2)