import pymodbus
from pymodbus.client import ModbusTcpClient

print(f"PyModbus version: {pymodbus.__version__}")

# Verify TCP client import works
client = ModbusTcpClient('127.0.0.1')
print("TCP client: OK")

# Verify serial client import (requires pymodbus[serial])
try:
    from pymodbus.client import ModbusSerialClient
    print("Serial client: OK")
except ImportError:
    print("Serial client: not installed (run pip install pymodbus[serial])")