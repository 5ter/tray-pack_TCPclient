"""Read-only test for PLC final inspection latches.

Run this first. It reads M7/M8, displays their values, and never writes to the
PLC, creates a database, sends data to a server, or prints a label.
"""

import logging
import time

from pymodbus.exceptions import ConnectionException, ModbusException

from tcp_v2_config import Settings
from tcp_v2_plc import LatchState, PlcLatchReader


def show_state(current: LatchState, previous: LatchState | None) -> None:
    if previous is None:
        print(f"Connected. Current state: M7 / OK = {current.ok}; M8 / NG = {current.ng}")
        print("Wait for an inspected tray. A state change will be displayed below.")
        return

    if current.ok != previous.ok:
        print(f"M7 / OK changed: {previous.ok} -> {current.ok}")
    if current.ng != previous.ng:
        print(f"M8 / NG changed: {previous.ng} -> {current.ng}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    reader = PlcLatchReader(settings)
    previous: LatchState | None = None

    print(f"Read-only test: PLC {settings.plc_ip}:{settings.plc_port}")
    print(f"Configured mapping: Modbus coil {settings.ok_coil_address} = M7 / OK")
    print(f"Configured mapping: Modbus coil {settings.ng_coil_address} = M8 / NG")
    print("Press Ctrl+C to stop. No PLC writes will be performed.")

    try:
        while True:
            try:
                if reader.connect():
                    current = reader.read_latches()
                    show_state(current, previous)
                    previous = current
            except (ConnectionException, ModbusException, OSError) as error:
                print(f"PLC communication error: {error}")
                reader.close()
                time.sleep(settings.reconnect_delay_seconds)
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        print("\nTest stopped.")
    finally:
        reader.close()


if __name__ == "__main__":
    main()
